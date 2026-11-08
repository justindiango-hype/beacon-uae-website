# BEACON Downtown Dubai: rebuild the OSM placeholder buildings as detailed architecture.
# Usage (from the repo root):
#   /Applications/Blender.app/Contents/MacOS/Blender -b --python tools/blender/build_dubai_city.py -- \
#       assets/burj_khalifa_web.glb assets/dubai_city_enhanced.glb
# Deterministic (fixed seeds). Builds with Blender 5.2; output is Draco-compressed.
# Keeps the Burj Khalifa (Object_4/Object_9 + their parents) and Terrain untouched; removes the
# baked sky dome/sun (hidden by the site anyway) and the 116 OSM meshes + their 115 tiny textures.
import bpy, bmesh, sys, math, random, os, tempfile
import numpy as np
from mathutils import Vector

SRC, OUT = sys.argv[-2], sys.argv[-1]
random.seed(7)
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=SRC)
scene = bpy.context.scene

osm_parent = bpy.data.objects['map_23.osm_buildings']
osm = [o for o in scene.objects if o.type == 'MESH' and o.parent == osm_parent]

# ---------- 1. merge the OSM meshes and find real buildings ----------
bm = bmesh.new()
for o in osm:
    t = bmesh.new(); t.from_mesh(o.data); t.transform(o.matrix_world)
    me = bpy.data.meshes.new('tmp'); t.to_mesh(me); t.free(); bm.from_mesh(me); bpy.data.meshes.remove(me)
bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=0.05)
bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method='BEAUTY', ngon_method='BEAUTY')
bm.normal_update(); bm.faces.ensure_lookup_table()

seen = set(); comps = []
for f0 in bm.faces:
    if f0.index in seen: continue
    stack = [f0]; comp = []
    while stack:
        f = stack.pop()
        if f.index in seen: continue
        seen.add(f.index); comp.append(f)
        for e in f.edges:
            for g in e.link_faces:
                if g.index not in seen: stack.append(g)
    comps.append(comp)

# ---------- 2. procedural facade textures ----------
TEX = 512
def make_img(name, arr):
    img = bpy.data.images.new(name, TEX, TEX, alpha=False)
    rgba = np.ones((TEX, TEX, 4), dtype=np.float32); rgba[..., :3] = np.clip(arr, 0, 1)
    img.pixels.foreach_set(rgba.ravel())
    path = os.path.join(TMPDIR, f'{name}.jpg')
    img.filepath_raw = path; img.file_format = 'JPEG'; img.save()
    bpy.data.images.remove(img)
    im = bpy.data.images.load(path); im.name = name
    return im

TMPDIR = tempfile.mkdtemp(prefix='beacon_city_')
rng = np.random.default_rng(3)
yy, xx = np.mgrid[0:TEX, 0:TEX] / TEX          # yy: 0 bottom-ish row index (image rows go bottom->top in Blender)
def noise(scale, amp):
    n = rng.random((TEX // scale + 1, TEX // scale + 1))
    n = np.kron(n, np.ones((scale, scale)))[:TEX, :TEX]
    return (n - .5) * amp

# Glass curtain wall: 4 panels x 4 floors per tile (6 m x 14.4 m). Neutral blue-grey, tinted per building.
def glass_tex():
    a = np.zeros((TEX, TEX, 3))
    px, fl = 4, 4
    u = (xx * px) % 1; v = (yy * fl) % 1
    pid = (np.floor(xx * px) * 7 + np.floor(yy * fl) * 13) % 5
    sky = 0.55 + 0.35 * v                         # vertical reflection gradient within each floor
    base = np.stack([0.40 + 0.06 * pid / 5, 0.48 + 0.06 * pid / 5, 0.58 + 0.05 * pid / 5], -1)
    a[:] = base * (0.75 + 0.45 * (sky[..., None] - 0.55))
    a += noise(32, 0.05)[..., None]
    spandrel = (v < 0.16)                          # opaque spandrel at each slab
    a[spandrel] = np.array([0.16, 0.18, 0.21])
    mull = (u < 0.035) | (u > 0.965) | (v < 0.025) | ((v > 0.155) & (v < 0.175))
    a[mull] = np.array([0.52, 0.54, 0.56])
    return a

# Residential facade: 4 bays x 3 floors per tile (12 m x 9.9 m): light walls, deep windows, balcony slabs.
def resi_tex():
    a = np.ones((TEX, TEX, 3)) * 0.62
    bays, fl = 4, 3
    u = (xx * bays) % 1; v = (yy * fl) % 1
    win = (u > 0.18) & (u < 0.82) & (v > 0.22) & (v < 0.86)
    a[win] = np.array([0.12, 0.16, 0.21]) + (0.16 * ((v[win] - .22) / .64))[:, None] * np.array([1, 1, 1.15])
    frame = win & ((u < 0.21) | (u > 0.79) | (v < 0.25) | (v > 0.83) | (np.abs(u - 0.5) < 0.012))
    a[frame] = np.array([0.55, 0.55, 0.54])
    slab = (v < 0.12)
    a[slab] = np.array([0.70, 0.69, 0.67])
    shadow = (v >= 0.12) & (v < 0.17)
    a[shadow] = a[shadow] * 0.6
    rail = (v >= 0.12) & (v < 0.30) & ~((u > .1) & (u < .9) & (v > .14) & (v < .28))
    a += noise(16, 0.035)[..., None]
    return a

# Low-rise plaster: 3 bays x 2 floors per tile (9 m x 7 m): punched windows with shadow lip.
def plaster_tex():
    a = np.ones((TEX, TEX, 3)) * 0.64 + noise(8, 0.04)[..., None] + noise(64, 0.04)[..., None]
    bays, fl = 3, 2
    u = (xx * bays) % 1; v = (yy * fl) % 1
    win = (u > 0.28) & (u < 0.72) & (v > 0.30) & (v < 0.80)
    a[win] = np.array([0.13, 0.17, 0.22]) + (0.14 * ((v[win] - .3) / .5))[:, None]
    lip = (u > 0.26) & (u < 0.74) & (v > 0.26) & (v <= 0.30)
    a[lip] = 0.70
    shade = (u > 0.28) & (u < 0.72) & (v > 0.74) & (v < 0.80)
    a[shade] *= 0.55
    band = (v < 0.05)
    a[band] *= 0.9
    return a

# Podium / storefront: tall dark glass bays with light stone piers.
def store_tex():
    a = np.ones((TEX, TEX, 3)) * np.array([0.60, 0.57, 0.52]) + noise(8, 0.03)[..., None]
    bays = 2
    u = (xx * bays) % 1; v = yy
    gl = (u > 0.12) & (u < 0.88) & (v > 0.08) & (v < 0.78)
    a[gl] = np.array([0.07, 0.09, 0.12]) + (0.12 * (v[gl] - .08))[:, None]
    tr = gl & ((np.abs(v - 0.62) < 0.008) | (np.abs(u - 0.5) < 0.006))
    a[tr] = np.array([0.55, 0.55, 0.55])
    canopy = (v > 0.78) & (v < 0.84)
    a[canopy] = np.array([0.30, 0.31, 0.33])
    return a

# Roof: concrete with gravel noise and joints.
def roof_tex():
    a = np.ones((TEX, TEX, 3)) * np.array([0.50, 0.49, 0.47]) + noise(4, 0.07)[..., None] + noise(64, 0.05)[..., None]
    joint = ((xx * 8) % 1 < 0.015) | ((yy * 8) % 1 < 0.015)
    a[joint] *= 0.8
    return a

IMG = {k: make_img('city_' + k, f()) for k, f in
       [('glass', glass_tex), ('resi', resi_tex), ('plaster', plaster_tex), ('store', store_tex), ('roof', roof_tex)]}

def make_mat(name, img, metallic, rough, double=False, color=(1, 1, 1, 1)):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; b = nt.nodes['Principled BSDF']
    b.inputs['Metallic'].default_value = metallic; b.inputs['Roughness'].default_value = rough
    vc = nt.nodes.new('ShaderNodeVertexColor'); vc.layer_name = 'Col'
    mix = nt.nodes.new('ShaderNodeMix'); mix.data_type = 'RGBA'; mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = 1.0
    if img:
        tx = nt.nodes.new('ShaderNodeTexImage'); tx.image = img
        nt.links.new(tx.outputs['Color'], mix.inputs['A'])
    else:
        mix.inputs['A'].default_value = color
    nt.links.new(vc.outputs['Color'], mix.inputs['B'])
    nt.links.new(mix.outputs['Result'], b.inputs['Base Color'])
    m.use_backface_culling = not double
    return m

MAT = {
    'glass': make_mat('City_Glass', IMG['glass'], 0.7, 0.12),
    'resi': make_mat('City_Residential', IMG['resi'], 0.0, 0.75),
    'plaster': make_mat('City_Plaster', IMG['plaster'], 0.0, 0.9),
    'store': make_mat('City_Podium', IMG['store'], 0.1, 0.45),
    'roof': make_mat('City_Roof', IMG['roof'], 0.0, 0.95),
    'metal': make_mat('City_Metal', None, 0.7, 0.3, double=True, color=(0.50, 0.52, 0.55, 1)),
}
TILE = {'glass': (6.0, 14.4), 'resi': (12.0, 9.9), 'plaster': (9.0, 7.0), 'store': (6.0, 6.0)}

# ---------- 3. geometry accumulator ----------
class Acc:
    def __init__(s): s.v = []; s.f = []; s.uv = []; s.col = []
ACC = {k: Acc() for k in MAT}

def quad(mat, pts, uvs, cols):
    a = ACC[mat]; i = len(a.v)
    a.v += pts; a.uv += uvs; a.col += cols
    a.f.append(tuple(range(i, i + len(pts))))

def ao(z, base):  # darker near the street, like ambient occlusion
    return 0.80 + 0.20 * min(1.0, max(0.0, (z - base) / 30.0))

def shade(tint, k):
    return (tint[0] * k, tint[1] * k, tint[2] * k, 1.0)

def walls(mat, loop, z0, z1, base, tint, skip=None, outward=True):
    tw, th = TILE.get(mat, (8.0, 8.0))
    n = len(loop); u = 0.0
    for i in range(n):
        a = loop[i]; b = loop[(i + 1) % n]
        L = math.hypot(b[0] - a[0], b[1] - a[1])
        if L < 1e-3: continue
        if skip and ekey(a, b) in skip: u += L; continue
        u0, u1 = u / tw, (u + L) / tw; v0, v1 = (z0 - base) / th, (z1 - base) / th
        c0, c1 = shade(tint, ao(z0, base)), shade(tint, ao(z1, base))
        if outward:
            quad(mat, [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)],
                 [(u0, v0), (u1, v0), (u1, v1), (u0, v1)], [c0, c0, c1, c1])
        else:
            quad(mat, [(b[0], b[1], z0), (a[0], a[1], z0), (a[0], a[1], z1), (b[0], b[1], z1)],
                 [(u1, v0), (u0, v0), (u0, v1), (u1, v1)], [c0, c0, c1, c1])
        u += L

def cap(mat, tris, z, tint, down=False):
    c = shade(tint, 1.0)
    for t in tris:
        pts = [(p[0], p[1], z) for p in (reversed(t) if down else t)]
        quad(mat, pts, [(p[0] / 20.0, p[1] / 20.0) for p in pts], [c] * 3)

def ring(mat, outer, inner, z, tint, up=True):
    c = shade(tint, 1.0); n = len(outer)
    for i in range(n):
        a, b = outer[i], outer[(i + 1) % n]; ai, bi = inner[i], inner[(i + 1) % n]
        pts = [(a[0], a[1], z), (b[0], b[1], z), (bi[0], bi[1], z), (ai[0], ai[1], z)]
        if not up: pts = pts[::-1]
        quad(mat, pts, [(p[0] / 20.0, p[1] / 20.0) for p in pts], [c] * 4)

def box(mat, cx, cy, sx, sy, z0, h, tint):
    lp = [(cx - sx, cy - sy), (cx + sx, cy - sy), (cx + sx, cy + sy), (cx - sx, cy + sy)]
    walls(mat, lp, z0, z0 + h, z0, tint)
    cap('roof' if mat != 'metal' else 'metal', [(lp[0], lp[1], lp[2]), (lp[0], lp[2], lp[3])], z0 + h, tint)

def mast(cx, cy, z0, h, r0, r1, seg=8):
    t = (0.82, 0.84, 0.87)
    for i in range(seg):
        a0 = 2 * math.pi * i / seg; a1 = 2 * math.pi * (i + 1) / seg
        p = [(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0), z0), (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1), z0),
             (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1), z0 + h), (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0), z0 + h)]
        quad('metal', p, [(0, 0)] * 4, [shade(t, 1)] * 4)

# ---------- polygon helpers ----------
def ekey(a, b):
    k1 = (round(a[0], 1), round(a[1], 1)); k2 = (round(b[0], 1), round(b[1], 1))
    return (k1, k2) if k1 < k2 else (k2, k1)

def area(loop):
    return 0.5 * sum(loop[i][0] * loop[(i + 1) % len(loop)][1] - loop[(i + 1) % len(loop)][0] * loop[i][1] for i in range(len(loop)))

def centroid(loop):
    A = area(loop)
    if abs(A) < 1e-6: return (sum(p[0] for p in loop) / len(loop), sum(p[1] for p in loop) / len(loop))
    cx = cy = 0
    for i in range(len(loop)):
        a, b = loop[i], loop[(i + 1) % len(loop)]; cr = a[0] * b[1] - b[0] * a[1]
        cx += (a[0] + b[0]) * cr; cy += (a[1] + b[1]) * cr
    return (cx / (6 * A), cy / (6 * A))

def inside(pt, loop):
    x, y = pt; c = False; n = len(loop)
    for i in range(n):
        a, b = loop[i], loop[(i + 1) % n]
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1] + 1e-12) + a[0]: c = not c
    return c

def offset(loop, d):
    """Offset to the left (into the roof) by d (negative = outward). Miter, clamped."""
    n = len(loop); out = []
    for i in range(n):
        p, c, q = loop[i - 1], loop[i], loop[(i + 1) % n]
        e1 = (c[0] - p[0], c[1] - p[1]); e2 = (q[0] - c[0], q[1] - c[1])
        l1 = math.hypot(*e1) or 1; l2 = math.hypot(*e2) or 1
        n1 = (-e1[1] / l1, e1[0] / l1); n2 = (-e2[1] / l2, e2[0] / l2)
        m = (n1[0] + n2[0], n1[1] + n2[1]); ml = math.hypot(*m)
        if ml < 1e-6: m = n1; ml = 1
        m = (m[0] / ml, m[1] / ml); dot = max(0.35, m[0] * n1[0] + m[1] * n1[1])
        dd = d / dot
        lim = 0.45 * min(l1, l2)
        dd = max(-lim * 2, min(lim, dd)) if d > 0 else max(-abs(d) * 2.5, dd)
        out.append((c[0] + m[0] * dd, c[1] + m[1] * dd))
    return out

def scale_about(loop, c, s):
    return [(c[0] + (p[0] - c[0]) * s, c[1] + (p[1] - c[1]) * s) for p in loop]

def scale_tris(tris, c, s):
    return [tuple((c[0] + (p[0] - c[0]) * s, c[1] + (p[1] - c[1]) * s) for p in t) for t in tris]

def sharp(loop, i, deg=35):
    p, c, q = loop[i - 1], loop[i], loop[(i + 1) % len(loop)]
    a1 = math.atan2(c[1] - p[1], c[0] - p[0]); a2 = math.atan2(q[1] - c[1], q[0] - c[0])
    d = abs((a2 - a1 + math.pi) % (2 * math.pi) - math.pi)
    return math.degrees(d) > deg

def simplify(loop, tol=0.25):
    out = []
    for i, p in enumerate(loop):
        if out and math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) < tol: continue
        out.append(p)
    if len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < tol: out.pop()
    return out

# ---------- 4. per-building analysis ----------
GLASS_TINTS = [(0.80, 0.90, 1.0), (0.74, 0.94, 0.96), (1.0, 1.0, 1.0), (0.98, 0.98, 1.0), (1.0, 0.88, 0.72), (0.66, 0.78, 0.95), (0.90, 0.95, 1.0)]
RESI_TINTS = [(1.0, 0.98, 0.94), (0.98, 0.93, 0.85), (0.95, 0.95, 0.95), (1.0, 0.95, 0.88), (0.92, 0.90, 0.86)]
PLAS_TINTS = [(0.98, 0.92, 0.82), (0.96, 0.89, 0.78), (1.0, 0.97, 0.92), (0.93, 0.86, 0.76), (0.99, 0.95, 0.88)]
STONE = (0.98, 0.95, 0.90)

stats = {'tower': 0, 'mid': 0, 'low': 0, 'pitched': 0, 'skipped': 0}

def roof_groups(comp):
    roofs = [f for f in comp if f.normal.z > 0.9]
    groups = {}
    for f in roofs:
        z = sum(v.co.z for v in f.verts) / 3
        groups.setdefault(round(z / 1.5), []).append(f)
    out = []
    for key, faces in groups.items():
        fs = set(faces); z = sum(v.co.z for f in faces for v in f.verts) / (3 * len(faces))
        directed = {}
        for f in faces:
            for l in f.loops:
                e = l.edge
                if sum(1 for g in e.link_faces if g in fs) == 1:
                    a = l.vert; b = l.link_loop_next.vert
                    directed.setdefault(a.index, []).append((b.index, (a.co.x, a.co.y), (b.co.x, b.co.y)))
        loops = []; used = set()
        for start in list(directed):
            for k, (nb, pa, pb) in enumerate(directed[start]):
                if (start, nb) in used: continue
                lp = []; cur = start; nxt = nb; ppa = pa
                guard = 0
                while guard < 5000:
                    guard += 1
                    used.add((cur, nxt)); lp.append(ppa)
                    if nxt == start: break
                    cand = [c for c in directed.get(nxt, []) if (nxt, c[0]) not in used]
                    if not cand: break
                    cur, (nxt, ppa, _) = nxt, cand[0]
                if len(lp) >= 3: loops.append(simplify(lp))
        loops = [l for l in loops if len(l) >= 3 and abs(area(l)) > 2.0]
        if not loops: continue
        tris = [tuple((v.co.x, v.co.y) for v in f.verts) for f in faces]
        out.append({'z': z, 'loops': loops, 'tris': tris, 'area': sum(area(l) for l in loops)})
    return out

for comp in comps:
    zs = [v.co.z for f in comp for v in f.verts]
    base = min(zs); top = max(zs); H = top - base
    if H < 1.5:
        stats['skipped'] += 1; continue
    pitched = any(0.15 < abs(f.normal.z) < 0.9 for f in comp)
    if pitched and H < 25:
        # villa with a pitched roof: already shaped; restyle (plaster walls, terracotta-free light roofs)
        tint = random.choice(PLAS_TINTS)
        for f in comp:
            pts = [tuple(v.co) for v in f.verts]
            if abs(f.normal.z) < 0.15:
                t = Vector((-f.normal.y, f.normal.x, 0))
                uvs = [((p[0] * t.x + p[1] * t.y) / TILE['plaster'][0], (p[2] - base) / TILE['plaster'][1]) for p in pts]
                quad('plaster', pts, uvs, [shade(tint, ao(p[2], base)) for p in pts])
            else:
                quad('roof', pts, [(p[0] / 20, p[1] / 20) for p in pts], [shade((0.93, 0.86, 0.78), 1)] * 3)
        stats['pitched'] += 1; continue

    blocks = roof_groups(comp)
    if not blocks:
        stats['skipped'] += 1; continue
    blocks.sort(key=lambda b: b['z'])
    tallest = blocks[-1]
    # edges a lower block shares with a taller block are interior: no wall there (avoids z-fighting)
    for i, b in enumerate(blocks):
        higher = set()
        for hb in blocks[i + 1:]:
            for lp in hb['loops']:
                for j in range(len(lp)): higher.add(ekey(lp[j], lp[(j + 1) % len(lp)]))
        b['skip'] = higher

    kind = 'tower' if H >= 75 else ('mid' if H >= 18 else 'low')
    stats[kind] += 1
    gt = random.choice(GLASS_TINTS); rt = random.choice(RESI_TINTS); pt = random.choice(PLAS_TINTS)

    for b in blocks:
        h = b['z'] - base; zt = b['z']
        if h < 1.0: continue
        outer = max(b['loops'], key=lambda l: abs(area(l)))
        c = centroid(outer)
        xs = [p[0] for p in outer]; ys = [p[1] for p in outer]
        span = min(max(xs) - min(xs), max(ys) - min(ys))
        is_top = b is tallest

        if kind == 'tower' and h >= 60:
            P = max(8.0, min(18.0, 0.10 * h))
            for lp in b['loops']: walls('store', lp, base, base + P, base, STONE, b['skip'])
            for lp in b['loops']:  # podium cornice
                o = offset(lp, -0.7)
                walls('metal', o, base + P, base + P + 0.9, base, (1, 1, 1))
                ring('metal', o, lp, base + P + 0.9, (1, 1, 1)); ring('metal', o, lp, base + P, (1, 1, 1), up=False)
            # tiers (setbacks keep the original height, step the silhouette in)
            if h > 150 and span > 18:
                cuts = [(base + P, base + 0.74 * h, 1.0), (base + 0.74 * h, base + 0.88 * h, max(0.7, 1 - 5.0 / span)),
                        (base + 0.88 * h, zt, max(0.55, 1 - 10.0 / span))]
            elif h > 100 and span > 14:
                cuts = [(base + P, base + 0.85 * h, 1.0), (base + 0.85 * h, zt, max(0.65, 1 - 6.0 / span))]
            else:
                cuts = [(base + P, zt, 1.0)]
            for ti, (z0, z1, s) in enumerate(cuts):
                lps = [scale_about(lp, c, s) for lp in b['loops']]
                for lp in lps: walls('glass', lp, z0, z1, base, gt, b['skip'] if s == 1.0 else None)
                last = ti == len(cuts) - 1
                if not last:
                    cap('roof', scale_tris(b['tris'], c, s), z1, (0.9, 0.9, 0.9))
                    for lp in lps:  # cornice at each setback
                        o = offset(lp, -0.4)
                        walls('metal', o, z1 - 0.7, z1 + 0.1, base, (1, 1, 1)); ring('metal', o, lp, z1 + 0.1, (1, 1, 1))
                if ti == 0 and s == 1.0:  # corner fins up the shaft
                    for lp in lps:
                        if len(lp) > 24: continue
                        for i in range(len(lp)):
                            if sharp(lp, i):
                                o = offset(lp, -0.45)[i]
                                box('metal', o[0], o[1], 0.45, 0.45, z0, z1 - z0, (1, 1, 1))
                if last:
                    cap('roof', scale_tris(b['tris'], c, s), z1, (0.92, 0.92, 0.9))
                    C = max(5.0, min(16.0, 0.045 * h))
                    for lp in lps: walls('metal', lp, z1, z1 + C, base, (1, 1, 1))  # open crown screen
                    if span * s > 8:  # rooftop plant inside the crown
                        box('resi', c[0], c[1], span * s * 0.16, span * s * 0.12, z1, min(C - 1, 4.5), (0.9, 0.9, 0.9))
                    if is_top and H > 200 and inside(c, lps[0]):
                        mast(c[0], c[1], z1, max(18.0, min(40.0, 0.11 * h)), 1.1, 0.12)
        elif kind in ('tower', 'mid') and h >= 12:
            P = 4.5
            for lp in b['loops']:
                walls('store', lp, base, base + P, base, STONE, b['skip'])
                walls('resi', lp, base + P, zt, base, rt, b['skip'])
            z = base + P + 9.9
            while z < zt - 4:  # balcony slab bands every 3 floors
                for lp in b['loops']:
                    if len(lp) > 40: continue
                    o = offset(lp, -0.45)
                    walls('resi', o, z, z + 0.5, base, (1.0, 1.0, 0.98))
                    ring('resi', o, lp, z + 0.5, (1.0, 1.0, 0.98)); ring('resi', o, lp, z, (0.8, 0.8, 0.8), up=False)
                z += 9.9
            cap('roof', b['tris'], zt, (0.9, 0.9, 0.88))
            for lp in b['loops']:  # parapet
                inn = offset(lp, 0.4)
                walls('resi', lp, zt, zt + 1.2, base, rt)
                walls('resi', inn, zt, zt + 1.2, base, rt, outward=False)
                ring('resi', lp, inn, zt + 1.2, rt)
            if is_top and span > 10 and inside(c, outer):
                box('resi', c[0], c[1], span * 0.14, span * 0.10, zt, 3.6, (0.92, 0.92, 0.9))
                for k in range(random.randint(1, 3)):
                    px, py = c[0] + random.uniform(-.25, .25) * span, c[1] + random.uniform(-.25, .25) * span
                    if inside((px, py), outer): box('metal', px, py, 1.1, 1.1, zt, 2.2, (1, 1, 1))
        else:
            mat = 'plaster'
            for lp in b['loops']: walls(mat, lp, base, zt, base, pt, b['skip'])
            cap('roof', b['tris'], zt, (0.93, 0.92, 0.89))
            for lp in b['loops']:
                inn = offset(lp, 0.3)
                walls(mat, lp, zt, zt + 0.9, base, pt)
                walls(mat, inn, zt, zt + 0.9, base, pt, outward=False)
                ring(mat, lp, inn, zt + 0.9, pt)
            if is_top and span > 8 and abs(b['area']) > 60:
                for k in range(random.randint(1, 2)):
                    px, py = c[0] + random.uniform(-.2, .2) * span, c[1] + random.uniform(-.2, .2) * span
                    if inside((px, py), outer): box('metal', px, py, 0.9, 0.7, zt, 1.4, (1, 1, 1))

bm.free()

# ---------- 5. build one mesh per material ----------
city = bpy.data.objects.new('Dubai_City', None); scene.collection.objects.link(city)
city.parent = osm_parent.parent
tri_total = 0
for k, a in ACC.items():
    if not a.f: continue
    me = bpy.data.meshes.new('City_' + k)
    me.from_pydata(a.v, [], a.f)
    uvl = me.uv_layers.new(name='UVMap')
    colattr = me.color_attributes.new('Col', 'FLOAT_COLOR', 'CORNER')
    for poly in me.polygons:
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            uvl.data[li].uv = a.uv[vi]; colattr.data[li].color = a.col[vi]
    me.color_attributes.active_color = colattr
    me.materials.append(MAT[k])
    me.validate(); me.update()
    for poly in me.polygons: poly.use_smooth = False
    ob = bpy.data.objects.new('City_' + k, me); scene.collection.objects.link(ob); ob.parent = city
    tri_total += sum(len(p.vertices) - 2 for p in me.polygons)

# ---------- 6. remove placeholders + baked sky ----------
for o in osm: bpy.data.objects.remove(o, do_unlink=True)
bpy.data.objects.remove(osm_parent, do_unlink=True)
for n in ('Golden_Hour_Sky_Dome', 'Golden_Hour_Sun'):
    if n in bpy.data.objects: bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
bpy.ops.outliner.orphans_purge(do_recursive=True)

print('CITY', stats, 'city tris', tri_total, 'meshes', {k: len(a.f) for k, a in ACC.items()})
bpy.ops.export_scene.gltf(
    filepath=OUT, export_format='GLB', export_image_format='AUTO',
    export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=7,
    export_draco_position_quantization=16, export_draco_normal_quantization=10,
    export_draco_texcoord_quantization=14, export_draco_color_quantization=8,
    export_vertex_color='ACTIVE', export_yup=True, export_apply=False)
print('EXPORTED', OUT)
