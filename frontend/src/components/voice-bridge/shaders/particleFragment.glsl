varying vec3 vColor;
varying float vAlpha;

void main() {
  float dist = length(gl_PointCoord - 0.5);
  if (dist > 0.5) discard;

  float alpha = (1.0 - dist * 2.0) * vAlpha;
  gl_FragColor = vec4(vColor, alpha);
}