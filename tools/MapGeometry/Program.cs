using System.Numerics;
using System.Text.Json;
using SteamDatabase.ValvePak;
using ValveResourceFormat;
using ValveResourceFormat.ResourceTypes;
using ValveResourceFormat.Serialization.KeyValues;

// Read-only conversion of the installed map's collision resource. No game process access.
try
{
if (args.Length != 2) throw new ArgumentException("MapGeometry <map.vpk> <output.bvh>");
using var package = new Package();
package.Read(args[0]);
Console.Error.WriteLine("stage: package opened");
var map = Path.GetFileNameWithoutExtension(args[0]);
var entry = package.FindEntry($"maps/{map}/world_physics.vphys_c")
    ?? package.FindEntry($"maps/{map}/world_physics.vmdl_c")
    ?? throw new InvalidDataException("World collision resource not found");
package.ReadEntry(entry, out var data);
Console.Error.WriteLine($"stage: collision resource ({data.Length} bytes)");
using var resource = new Resource();
resource.Read(new MemoryStream(data));
Console.Error.WriteLine("stage: resource decoded");
var physics = resource.Blocks.OfType<PhysAggregateData>().FirstOrDefault()
    ?? throw new InvalidDataException("Unsupported collision resource");
var allowed = new bool[physics.CollisionAttributes.Count];
var attributes = new List<object>();
for (int i = 0; i < allowed.Length; i++)
{
    var attr = physics.CollisionAttributes[i];
    var tags = attr.GetArray<string>("m_InteractAsStrings") ?? attr.GetArray<string>("m_PhysicsTagStrings") ?? [];
    var group = attr.GetStringProperty("m_CollisionGroupString") ?? "";
    // Solid and bullet-blocking geometry only; playerclip / triggers are not walls.
    allowed[i] = (tags.Length == 0 && !group.Contains("trigger",StringComparison.OrdinalIgnoreCase))
        || tags.Any(t => t is "solid" or "bulletclip" or "blocklos");
    attributes.Add(new { index = i, tags, group, included = allowed[i] });
}
var triangles = new List<Tri>();
var curves = new List<(Vector3 Start,Vector3 End,float Radius)>();
Console.Error.WriteLine($"stage: {physics.Parts.Length} parts");
int hulls = 0, meshes = 0;
bool Include(int index) => index >= 0 && index < allowed.Length && allowed[index];
void Add(Vector3 a, Vector3 b, Vector3 c)
{
    if (!float.IsFinite(a.X + a.Y + a.Z + b.X + b.Y + b.Z + c.X + c.Y + c.Z))
        throw new InvalidDataException("Non-finite geometry");
    if (Vector3.Cross(b-a, c-a).LengthSquared() > 1e-10f) triangles.Add(new(a,b,c));
}
for (int p = 0; p < physics.Parts.Length; p++)
{
    var shape = physics.Parts[p].Shape;
    var pose = physics.BindPose.Length == 0 ? Matrix4x4.Identity : physics.BindPose[p];
    foreach (var mesh in shape.Meshes)
    {
        if (!Include(mesh.CollisionAttributeIndex)) continue;
        meshes++;
        var vertices = mesh.Shape.GetVertices().ToArray().Select(v => Vector3.Transform(v,pose)).ToArray();
        foreach (var tri in mesh.Shape.GetTriangles()) Add(vertices[tri.X],vertices[tri.Y],vertices[tri.Z]);
    }
    foreach (var hull in shape.Hulls)
    {
        if (!Include(hull.CollisionAttributeIndex)) continue;
        hulls++;
        var vertices = hull.Shape.GetVertexPositions().ToArray().Select(v => Vector3.Transform(v,pose)).ToArray();
        var edges = hull.Shape.GetEdges();
        foreach (var face in hull.Shape.GetFaces())
        {
            int start = face.Edge, e = edges[start].Next, budget = edges.Length;
            while (e != start && budget-- > 0)
            {
                int next = edges[e].Next;
                if (next == start) break;
                Add(vertices[edges[start].Origin], vertices[edges[e].Origin], vertices[edges[next].Origin]);
                e = next;
            }
            if (budget <= 0) throw new InvalidDataException("Invalid hull edge cycle");
        }
    }
    float scale = MathF.Max(new Vector3(pose.M11,pose.M12,pose.M13).Length(),
                  MathF.Max(new Vector3(pose.M21,pose.M22,pose.M23).Length(),new Vector3(pose.M31,pose.M32,pose.M33).Length()));
    foreach(var sphere in shape.Spheres.Where(s=>Include(s.CollisionAttributeIndex)))
    {
        var center=Vector3.Transform(sphere.Shape.Center,pose);
        curves.Add((center,center,sphere.Shape.Radius*scale));
    }
    foreach(var capsule in shape.Capsules.Where(s=>Include(s.CollisionAttributeIndex)))
        curves.Add((Vector3.Transform(capsule.Shape.Center[0],pose),Vector3.Transform(capsule.Shape.Center[1],pose),capsule.Shape.Radius*scale));
}
if (triangles.Count < 10)
{
    Console.Error.WriteLine(JsonSerializer.Serialize(new {parts=physics.Parts.Length, attributes}));
    foreach(var attr in physics.CollisionAttributes) Console.Error.WriteLine(attr.ToString());
    throw new InvalidDataException("Map collision is empty");
}
var tris = triangles.ToArray();
Console.Error.WriteLine($"stage: {tris.Length} triangles; building BVH");
var nodes = new List<Node>();
int Build(int start, int count)
{
    var min = new Vector3(float.PositiveInfinity);
    var max = new Vector3(float.NegativeInfinity);
    var cmin = min; var cmax = max;
    for (int i=start; i<start+count; i++)
    {
        min = Vector3.Min(min,tris[i].Min); max=Vector3.Max(max,tris[i].Max);
        cmin=Vector3.Min(cmin,tris[i].Center); cmax=Vector3.Max(cmax,tris[i].Center);
    }
    int index=nodes.Count;
    nodes.Add(new(min,max,-1,-1,start,count));
    if (count>8)
    {
        var span=cmax-cmin;
        int axis=span.X>span.Y ? (span.X>span.Z?0:2) : (span.Y>span.Z?1:2);
        int mid=count/2;
        // In-place median selection: avoid sorting every subtree on large maps.
        int lo=start, hi=start+count-1, median=start+mid;
        while(lo<hi)
        {
            float pivot=tris[(lo+hi)/2].Center[axis];
            int a=lo,b=hi;
            while(a<=b)
            {
                while(tris[a].Center[axis]<pivot) a++;
                while(tris[b].Center[axis]>pivot) b--;
                if(a<=b) {(tris[a],tris[b])=(tris[b],tris[a]);a++;b--;}
            }
            if(median<=b) hi=b;
            else if(median>=a) lo=a;
            else break;
        }
        int left=Build(start,mid), right=Build(start+mid,count-mid);
        nodes[index]=new(min,max,left,right,0,0);
    }
    return index;
}
Build(0,tris.Length);
Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(args[1]))!);
var temp=args[1]+".tmp";
using (var writer=new BinaryWriter(File.Create(temp)))
{
    writer.Write("CS2BVH02"u8); writer.Write(nodes.Count); writer.Write(tris.Length);
    void Vec(Vector3 v) {writer.Write(v.X);writer.Write(v.Y);writer.Write(v.Z);}
    foreach (var n in nodes) {Vec(n.Min);Vec(n.Max);writer.Write(n.Left);writer.Write(n.Right);writer.Write(n.Start);writer.Write(n.Count);}
    foreach (var t in tris) {Vec(t.A);Vec(t.B-t.A);Vec(t.C-t.A);}
    writer.Write(curves.Count);
    foreach(var curve in curves) {Vec(curve.Start);Vec(curve.End);writer.Write(curve.Radius);}
}
File.Move(temp,args[1],true);
Console.WriteLine(JsonSerializer.Serialize(new {map,triangles=tris.Length,nodes=nodes.Count,hulls,meshes,curves=curves.Count,attributes}));

}
catch(Exception error)
{
    Console.Error.WriteLine(error.Message);
    Environment.ExitCode=1;
}

record struct Tri(Vector3 A,Vector3 B,Vector3 C)
{
    public Vector3 Min=>Vector3.Min(A,Vector3.Min(B,C));
    public Vector3 Max=>Vector3.Max(A,Vector3.Max(B,C));
    public Vector3 Center {get;}=(A+B+C)/3;
}
record struct Node(Vector3 Min,Vector3 Max,int Left,int Right,int Start,int Count);
