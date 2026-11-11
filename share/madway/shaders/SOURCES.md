# External shader sources

The following GPUImage2 image filters are adapted to madway's session renderer.
Source: [BradLarson/GPUImage2](https://github.com/BradLarson/GPUImage2), pinned
revision `3a2275e48716a6ebdab0d4098bd7d90321ef4143`. The BSD-3-Clause notice is shipped at
`../licenses/GPUImage2-BSD-3-Clause.txt` and retained in each adapted fragment.

| madway shader | Original filter |
| --- | --- |
| Zoom defocus | [ZoomBlur](https://github.com/BradLarson/GPUImage2/blob/3a2275e48716a6ebdab0d4098bd7d90321ef4143/framework/Source/Operations/Shaders/ZoomBlur_GLES.fsh) |
| Polar crystal | [PolarPixellate](https://github.com/BradLarson/GPUImage2/blob/3a2275e48716a6ebdab0d4098bd7d90321ef4143/framework/Source/Operations/Shaders/PolarPixellate_GLES.fsh) |
| Pinch lens | [PinchDistortion](https://github.com/BradLarson/GPUImage2/blob/3a2275e48716a6ebdab0d4098bd7d90321ef4143/framework/Source/Operations/Shaders/PinchDistortion_GLES.fsh) |
| Crosshatch raster | [Crosshatch](https://github.com/BradLarson/GPUImage2/blob/3a2275e48716a6ebdab0d4098bd7d90321ef4143/framework/Source/Operations/Shaders/Crosshatch_GLES.fsh) |

Adaptations: GLES2 uniform/sampler names, animated filter parameters, center-angle
stability, and a bounded fade to the session dark color with exact endpoints.
Opening runs the same effect in reverse. No GPUImage runtime is required.
The GL Transitions collection was reviewed and rejected; none of its code is used.
