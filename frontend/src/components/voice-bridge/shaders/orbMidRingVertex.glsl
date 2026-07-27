// orbMidRingVertex.glsl — Living Orb Mid Ring Vertex Shader
// Renders a ring geometry with UVs for conic gradient

varying vec2 vUv;
varying vec3 vWorldPosition;
varying vec3 vViewPosition;

uniform float uTime;
uniform float uMicLevel;
uniform vec3 uStateColor;
uniform vec3 uBrandColor;
uniform vec3 uAccentColor;
uniform float uRingRotation;
uniform float uBlobAmount;

void main() {
  vUv = uv;
  vec4 worldPos = modelMatrix * vec4(position, 1.0);
  vWorldPosition = worldPos.xyz;
  vViewPosition = (viewMatrix * worldPos).xyz;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}