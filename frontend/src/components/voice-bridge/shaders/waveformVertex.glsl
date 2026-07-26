varying vec2 vUv;

uniform sampler2D uWaveTexture;
uniform float uWaveAmplitude;

void main() {
  vUv = uv;
  vec3 pos = position;
  float waveSample = texture2D(uWaveTexture, vec2(uv.x, 0.5)).r;
  pos.y += (waveSample - 0.5) * uWaveAmplitude * 2.0;
  gl_Position = projectionMatrix * modelViewMatrix * vec4(pos, 1.0);
}