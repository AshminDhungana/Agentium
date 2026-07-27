// orbSurfaceVertex.glsl — Living Orb Inner Core Vertex Shader
// Passes through UV, normal, world position for fragment shader

varying vec3 vNormal;
varying vec2 vUv;
varying vec3 vWorldPosition;
varying vec3 vViewPosition;

void main() {
  vNormal = normalize(normalMatrix * normal);
  vUv = uv;
  vec4 worldPos = modelMatrix * vec4(position, 1.0);
  vWorldPosition = worldPos.xyz;
  vViewPosition = (viewMatrix * worldPos).xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}