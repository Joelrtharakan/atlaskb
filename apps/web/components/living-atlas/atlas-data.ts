/**
 * Deterministic constellation layout for the ambient Living Atlas.
 *
 * This is placeholder cartography: nodes and edges are generated from a fixed
 * seed so the map is stable across renders. In a later phase these positions
 * will come from a real embedding layout (e.g. UMAP) of a tenant's documents,
 * so spatial proximity reflects semantic proximity. Nothing here talks to the
 * API yet.
 */

export interface AtlasNode {
  /** World-space position. */
  position: [number, number, number];
  /** Relative size (stands in for chunk count). */
  scale: number;
}

export interface AtlasEdge {
  /** Indices into the node array. */
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

/**
 * Distribute points on a sphere via a jittered Fibonacci lattice, then flatten
 * z so the field reads like a chart plate rather than a dense ball.
 */
export function buildAtlas(
  count = 64,
  seed = 20260806,
  radius = 5,
): { nodes: AtlasNode[]; edges: AtlasEdge[] } {
  const rand = mulberry32(seed);
  const golden = Math.PI * (3 - Math.sqrt(5));
  const nodes: AtlasNode[] = [];

  for (let i = 0; i < count; i++) {
    const y = 1 - (i / (count - 1)) * 2; // 1 → -1
    const r = Math.sqrt(1 - y * y);
    const theta = golden * i;

    const jitter = () => (rand() - 0.5) * 0.35;
    const x = (Math.cos(theta) * r + jitter()) * radius;
    const yy = (y + jitter()) * radius;
    const z = (Math.sin(theta) * r + jitter()) * radius * 0.55; // flattened

    nodes.push({
      position: [x, yy, z],
      scale: 0.06 + rand() * 0.12,
    });
  }

  // Connect each node to its 2 nearest neighbours; dedupe undirected edges.
  const edgeKeys = new Set<string>();
  const edges: AtlasEdge[] = [];
  for (let i = 0; i < count; i++) {
    const dists: { j: number; d: number }[] = [];
    for (let j = 0; j < count; j++) {
      if (i === j) continue;
      const [ax, ay, az] = nodes[i].position;
      const [bx, by, bz] = nodes[j].position;
      const d = (ax - bx) ** 2 + (ay - by) ** 2 + (az - bz) ** 2;
      dists.push({ j, d });
    }
    dists.sort((p, q) => p.d - q.d);
    for (const { j } of dists.slice(0, 2)) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`;
      if (edgeKeys.has(key)) continue;
      edgeKeys.add(key);
      edges.push({ a: i, b: j });
    }
  }

  return { nodes, edges };
}
