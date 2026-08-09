/**
 * Northwind Survey — shared 3D primitive library.
 *
 * Every per-page treatment composes these five data-driven primitives (plus the
 * AtlasCanvas wrapper) rather than introducing bespoke geometry, so the whole
 * site reads as one world. Pages should lazy-load the component that renders an
 * AtlasCanvas via `dynamic(() => import(...), { ssr: false })`.
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
export {
  CoreSampleStack,
  type CoreSampleStackProps,
  type CoreLayer,
} from "./CoreSampleStack";
