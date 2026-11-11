// IFC uses Z up; Three.js controls and the ground grid use Y up.
// Apply only at the scene boundary. Server meshes and quantities stay in IFC space.
export const IFC_VIEW_ROTATION: [number, number, number] = [-Math.PI / 2, 0, 0];
