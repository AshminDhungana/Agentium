attribute vec3 velocity;
attribute float baseSize;
attribute vec3 baseColor;
attribute float phase;

uniform float uTime;
uniform float uDelta;
uniform float uMicLevel;
uniform int uState; // 0=idle, 1=listening, 2=speaking, 3=processing

varying vec3 vColor;
varying float vAlpha;

void main() {
  vec3 pos = position;
  float t = uTime;

  if (uState == 1) { // listening - attract to center
    vec3 toCenter = -pos;
    pos += toCenter * uDelta * 0.5 * uMicLevel;
    pos += velocity * uDelta * 0.1;
  } else if (uState == 2) { // speaking - explode outward
    pos += velocity * uDelta * 2.0 * (1.0 + uMicLevel);
  } else if (uState == 3) { // processing - spiral
    float angle = t * 0.5 + phase;
    mat2 rot = mat2(cos(angle), -sin(angle), sin(angle), cos(angle));
    pos.xz = rot * pos.xz;
    pos.y += sin(t * 2.0 + phase) * 0.02;
  } else { // idle - gentle drift
    pos += vec3(sin(t + phase) * 0.01, cos(t * 0.7 + phase) * 0.01, 0.0);
  }

  vec4 mvPos = modelViewMatrix * vec4(pos, 1.0);
  float size = baseSize * (1.0 + uMicLevel * 2.0) * (300.0 / length(mvPos.xyz));
  gl_PointSize = size;
  gl_Position = projectionMatrix * mvPos;

  vColor = baseColor;
  vAlpha = 0.3 + 0.7 * uMicLevel;
}