varying vec2 vUv;

uniform vec3 uColor;
uniform float uTime;

void main() {
  vec3 color = uColor * mix(0.2, 1.0, vUv.y);
  float grid = step(0.98, fract(vUv.x * 200.0)) + step(0.95, fract(vUv.y * 40.0));
  color = mix(color, uColor * 1.5, grid * 0.3);
  float alpha = 0.4 + 0.3 * vUv.y;
  gl_FragColor = vec4(color, alpha);
}