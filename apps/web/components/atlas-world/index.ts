/**
 * Northwind Survey — shared 3D primitive library.
 *
 * Every per-page treatment composes these data-driven primitives (plus the
 * AtlasCanvas wrapper) rather than introducing bespoke geometry, so the whole
 * site reads as one world. Pages should lazy-load the component that renders an
 * AtlasCanvas via `dynamic(() => import(...), { ssr: false })`.
 *
 * (The Document Detail "core sample" used to live here as a 3D cylinder —
 * CoreSampleStack — but WebGL couldn't scale to a real chunk count without
 * becoming illegible slivers; it's now a 2D stratigraphy column in
 * components/documents/CoreSample.tsx, no WebGL dependency at all.)
 */
export { ATLAS, type AtlasColor } from "./tokens";
export { AtlasCanvas, type AtlasCanvasProps } from "./AtlasCanvas";
export { TerrainField, type TerrainFieldProps, type TerrainMarker } from "./TerrainField";
export { CompassInstrument, type CompassInstrumentProps } from "./CompassInstrument";
export {
  ThreadField,
  type ThreadFieldProps,
  type ThreadNode,
  type ThreadEdge,
} from "./ThreadField";
export { FogLayer, type FogLayerProps, type FogPatch } from "./FogLayer";
