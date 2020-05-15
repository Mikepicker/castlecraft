#version 330 core

#define LUMA_THRESHOLD 0.5
#define MUL_REDUCE (1 / 8.0)
#define MIN_REDUCE (1 / 128.0)
#define MAX_SPAN 8
#define GAMMA 2.2

in vec2 TexCoords;
out vec3 FragColor;

uniform sampler2D frame;

uniform int width;
uniform int height;

uniform int fxaa_enabled;

vec3 fxaa() {
  vec2 u_texelStep = vec2(1 / width, 1 / height);

  vec3 rgbM = texture(frame, TexCoords).rgb;

  // Sampling neighbour texels. Offsets are adapted to OpenGL texture coordinates. 
  vec3 rgbNW = textureOffset(frame, TexCoords, ivec2(-1, 1)).rgb;
  vec3 rgbNE = textureOffset(frame, TexCoords, ivec2(1, 1)).rgb;
  vec3 rgbSW = textureOffset(frame, TexCoords, ivec2(-1, -1)).rgb;
  vec3 rgbSE = textureOffset(frame, TexCoords, ivec2(1, -1)).rgb;

  // see http://en.wikipedia.org/wiki/Grayscale
  const vec3 toLuma = vec3(0.299, 0.587, 0.114);

  // Convert from RGB to luma.
  float lumaNW = dot(rgbNW, toLuma);
  float lumaNE = dot(rgbNE, toLuma);
  float lumaSW = dot(rgbSW, toLuma);
  float lumaSE = dot(rgbSE, toLuma);
  float lumaM = dot(rgbM, toLuma);

  // Gather minimum and maximum luma.
  float lumaMin = min(lumaM, min(min(lumaNW, lumaNE), min(lumaSW, lumaSE)));
  float lumaMax = max(lumaM, max(max(lumaNW, lumaNE), max(lumaSW, lumaSE)));

  // If contrast is lower than a maximum threshold ...
  if (lumaMax - lumaMin <= lumaMax * LUMA_THRESHOLD) {
    // ... do no AA and return.
    return rgbM;
  }

  // Sampling is done along the gradient.
  vec2 samplingDirection;	
  samplingDirection.x = -((lumaNW + lumaNE) - (lumaSW + lumaSE));
  samplingDirection.y =  ((lumaNW + lumaSW) - (lumaNE + lumaSE));

  // Sampling step distance depends on the luma: The brighter the sampled texels, the smaller the final sampling step direction.
  // This results, that brighter areas are less blurred/more sharper than dark areas.  
  float samplingDirectionReduce = max((lumaNW + lumaNE + lumaSW + lumaSE) * 0.25 * MUL_REDUCE, MIN_REDUCE);

  // Factor for norming the sampling direction plus adding the brightness influence. 
  float minSamplingDirectionFactor = 1.0 / (min(abs(samplingDirection.x), abs(samplingDirection.y)) + samplingDirectionReduce);

  // Calculate final sampling direction vector by reducing, clamping to a range and finally adapting to the texture size. 
  samplingDirection = clamp(samplingDirection * minSamplingDirectionFactor, vec2(-MAX_SPAN), vec2(MAX_SPAN)) * u_texelStep;

  // Inner samples on the tab.
  vec3 rgbSampleNeg = texture(frame, TexCoords + samplingDirection * (1.0/3.0 - 0.5)).rgb;
  vec3 rgbSamplePos = texture(frame, TexCoords + samplingDirection * (2.0/3.0 - 0.5)).rgb;

  vec3 rgbTwoTab = (rgbSamplePos + rgbSampleNeg) * 0.5;  

  // Outer samples on the tab.
  vec3 rgbSampleNegOuter = texture(frame, TexCoords + samplingDirection * (0.0/3.0 - 0.5)).rgb;
  vec3 rgbSamplePosOuter = texture(frame, TexCoords + samplingDirection * (3.0/3.0 - 0.5)).rgb;

  vec3 rgbFourTab = (rgbSamplePosOuter + rgbSampleNegOuter) * 0.25 + rgbTwoTab * 0.5;   

  // Calculate luma for checking against the minimum and maximum value.
  float lumaFourTab = dot(rgbFourTab, toLuma);

  // Are outer samples of the tab beyond the edge ... 
  if (lumaFourTab < lumaMin || lumaFourTab > lumaMax) {
    // ... yes, so use only two samples.
    // rgbTwoTab.r = 1.0;
    return rgbTwoTab; 
  }
  else {
    // ... no, so use four samples. 
    // rgbFourTab.r = 1.0;
    return rgbFourTab;
  }
}

vec3 uncharted2Tonemap(vec3 x) {
	const float A = 0.15;
	const float B = 0.50;
	const float C = 0.10;
	const float D = 0.20;
	const float E = 0.02;
	const float F = 0.30;
	return ((x * (A * x + C * B) + D * E) / (x * (A * x + B) + D * F)) - E / F;
}

vec3 acesFilmTonemap(vec3 x) {
    const float a = 2.51;
    const float b = 0.03;
    const float c = 2.43;
    const float d = 0.59;
    const float e = 0.14;
    return clamp((x * (a * x + b)) / (x * (c * x + d ) + e), 0.0, 1.0);
}

vec3 reinhardTonemap(vec3 x) {
  return x / (x + vec3(1.0));
  // return vec3(1.0) - exp(-x);
}

void main() {
  FragColor = texture(frame, TexCoords).rgb;

  // Toggle FXAA on and off.
  if (fxaa_enabled == 1) {
    FragColor = fxaa(); 
  }

  // Tonemap
  FragColor = acesFilmTonemap(FragColor);

  // Gamma correction
  FragColor = pow(FragColor, vec3(1.0 / GAMMA));
}