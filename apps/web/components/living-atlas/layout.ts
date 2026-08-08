/**
 * Deterministic constellation layouts for the Living Atlas.
 *
 * Ambient mode (landing) uses a generative field. Functional mode (chat) maps
 * each of the tenant's real documents to a node, positioned with a stable,
 * pleasant arrangement (a jittered Fibonacci lattice flattened toward a chart
 * plate) so the map never looks random or cluttered. Positions are seeded from
 * document ids so a given corpus always lays out the same way.
 */

export interface AtlasNode {
  /** Stable identity — a real document id in functional mode. */
  id: string;
  /** Human label shown in the 2D fallback and (optionally) as billboards. */
  title: string;
  /** World-space position. */
  position: [number, number, number];
  /** Relative size (stands in for chunk count / prominence). */
  scale: number;
}

export interface AtlasEdge {
  a: number;
  b: number;
}

/** Small, fast, seedable PRNG (mulberry32). */
function mulberry32(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let x = t;
    x = Math.imul(x ^ (x >>> 15), x | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

/** Deterministic 32-bit hash of a string (FNV-1a). */
function hashString(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Positions on a jittered Fibonacci lattice, flattened in z (chart plate). */
function fibonacciPositions(
  count: number,
  rand: () => number,
  radius: number,
  flatten = 0.7,
): [number, number, number][] {
  const golden = Math.PI * (3 - Math.sqrt(5));
  const out: [number, number, number][] = [];
  for (let i = 0; i < count; i++) {
    const y = count === 1 ? 0 : 1 - (i / (count - 1)) * 2; // 1 → -1
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const theta = golden * i;
    // Distribute through a spherical *volume* (cube-root keeps it uniform) so the
    // field reads as a constellation with depth rather than a hollow shell.
    const shell = 0.45 + 0.55 * Math.cbrt(rand());
    const jitter = () => (rand() - 0.5) * 0.14;
    const x = (Math.cos(theta) * r * shell + jitter()) * radius;
    const yy = (y * shell + jitter()) * radius;
    const z = (Math.sin(theta) * r * shell + jitter()) * radius * flatten;
    out.push([x, yy, z]);
  }

  // Recenter on the true centroid so the cloud is symmetric about the origin —
  // this keeps it centered in the viewport under rotation and keeps the
  // functional camera framing accurate.
  const n = out.length || 1;
  const mean = out.reduce(
    (m, [px, py, pz]) => [m[0] + px / n, m[1] + py / n, m[2] + pz / n],
    [0, 0, 0],
  );
  return out.map(([px, py, pz]) => [px - mean[0], py - mean[1], pz - mean[2]]);
}

/** Connect each node to its ``k`` nearest neighbours; dedupe undirected edges. */
function nearestEdges(positions: [number, number, number][], k = 2): AtlasEdge[] {
  const edgeKeys = new Set<string>();
  const edges: AtlasEdge[] = [];
  for (let i = 0; i < positions.length; i++) {
    const dists: { j: number; d: number }[] = [];
    for (let j = 0; j < positions.length; j++) {
      if (i === j) continue;
      const [ax, ay, az] = positions[i];
      const [bx, by, bz] = positions[j];
      dists.push({ j, d: (ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2 });
    }
    dists.sort((p, q) => p.d - q.d);
    for (const { j } of dists.slice(0, k)) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (edgeKeys.has(key)) continue;
      edgeKeys.add(key);
      edges.push({ a: i, b: j });
    }
  }
  return edges;
}

/** Generative ambient field for the landing page (no real data). */
export function generativeAtlas(
  count = 84,
  seed = 20260807,
  radius = 4.4,
): { nodes: AtlasNode[]; edges: AtlasEdge[] } {
  const rand = mulberry32(seed);
  const positions = fibonacciPositions(count, rand, radius, 0.72);
  const nodes: AtlasNode[] = positions.map((position, i) => {
    // Size nodes by depth (nearer = larger) for a parallax, three-dimensional feel.
    const depth = (position[2] / (radius * 0.72) + 1) / 2; // 0 (far) → 1 (near)
    return {
      id: `ambient-${i}`,
      title: "",
      position,
      scale: 0.05 + depth * 0.1 + rand() * 0.025,
    };
  });
  // Two nearest-neighbour links per node give the pulses a richer route network.
  return { nodes, edges: nearestEdges(positions, 2) };
}

export interface DocumentLike {
  id: string;
  filename?: string;
  title?: string;
}

/**
 * Lay out a tenant's real documents. Order is stabilised by hashing ids so the
 * arrangement is deterministic regardless of fetch order, and the seed is
 * derived from the corpus so different corpora look distinct but stable.
 */
export function layoutFromDocuments(
  docs: DocumentLike[],
  radius = 4.2,
): { nodes: AtlasNode[]; edges: AtlasEdge[] } {
  const ordered = [...docs].sort((a, b) => hashString(a.id) - hashString(b.id));
  const seed = ordered.reduce((acc, d) => (acc ^ hashString(d.id)) >>> 0, 0x9e3779b9);
  const rand = mulberry32(seed || 1);
  const positions = fibonacciPositions(ordered.length, rand, radius);
  const nodes: AtlasNode[] = ordered.map((d, i) => ({
    id: d.id,
    title: d.title ?? d.filename ?? "Untitled",
    position: positions[i],
    // Slight, deterministic size variation so the field has texture.
    scale: 0.1 + ((hashString(d.id) % 100) / 100) * 0.08,
  }));
  return { nodes, edges: nearestEdges(positions, 2) };
}
