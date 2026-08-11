# MVTec AD 2 Public Benchmark

This report is generated only from the canonical aggregate JSON artifacts.
Raw images, anomaly maps, checkpoints, and private outputs are not included.

- Public benchmark SHA-256: `9cf47070c75bbf66f5e9919c32b5847b886a2f02190ea844c55273bb5ac4f751`
- Champions SHA-256: `813c9822d951a011706f8ecbcd35ea1531474be5a73039053f70270a9d7f05f2`
- Dataset manifest SHA-256: `557fd46fcfaa1c2618be315bced7f9f0ba381d8f45119929a200a9d12d1895bf`
- Public gate SHA-256: `5cb50fd6e7226ebccfdf3564d494d1890458fbcb29e8b3ae3182130ddfcc2409`
- Common pixel evaluation size: `256x256`

## Frozen category champions

| Category | Champion | Mean AU-PRO | Mean image AUROC | GPU p95 ms | Peak VRAM MiB | Artifact bytes | Selection reason | Run evidence |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| can | patchcore | 0.308051 | 0.510802 | 105.357 | 2146.338 | 1136661491 | significant_higher_au_pro | `3147a91e6d2c6536494edfa04985ba23490604f86f4c3e685a1ab18e94655b58`<br>`597dbe614d9aa98fd8939b0626aaf61def78fa4abac1b25755aeb5b5c980e81a`<br>`dc06f3aff0c13e17d1e9e4f9e59190121154e36c5b516fbe1527f759f841b57c` |
| fabric | dinomaly | 0.673491 | 0.711841 | 88.827 | 659.867 | 1329034063 | significant_higher_au_pro | `8c8de411b36904e7be61eebe0b6942876a2615690f1f26e6f43a519cbb47b954`<br>`b96429546f4bb46d528156e305cee5efd18be8e1f96513ba615d867879572a1f`<br>`4ff70550f063b796ddf9e4dba253281505d6b0dc80f00c97783c1db27b810857` |
| fruit_jelly | dinomaly | 0.727061 | 0.785556 | 64.844 | 659.293 | 1329000079 | significant_higher_au_pro | `de31a953ae314b31a6c9923d5b6a24b87b1f71c0aa4abc99b607e06b21755e5c`<br>`8a3b687e9da2e93e7f407aa0496cee17482302ce02faf1343e785e6d6e33bcde`<br>`f434284473c1de94e916147b1591a30c1a15253f304e2b4362c1130a1fea913a` |
| rice | dinomaly | 0.676754 | 0.682143 | 84.863 | 659.867 | 1329014287 | significant_higher_au_pro | `fb47a348c19f0def019df9b48c81255fc660371f4b2e16b82f2a0c0862bac403`<br>`d47baf7b7871fc45185753bee4a526ead9194847200612e48c241c2511aab726`<br>`eff5d6760d83c14ee03159642896aa61f575a03b8039063fff7e12070f41dfae` |
| sheet_metal | dinomaly | 0.495309 | 0.770370 | 73.688 | 659.293 | 1328966031 | significant_higher_au_pro | `07ec8896cd3258251575d9369564567d13fc5a229c1e46b860dcd0b04d82bb7a`<br>`fe366c4598620920e434af345569ffcd30941dd1621379249eb4e8a44d89cac7`<br>`6683a098b5612b26d5a31778eb45a4f831a4d3f53d51ae7aa20222286a22da25` |
| vial | patchcore | 0.924168 | 0.868753 | 74.254 | 1566.344 | 832152563 | significant_higher_au_pro | `41be15f350a3cd6e198810074bc7bf56e69e14550cab0b15d81f3067204af948`<br>`8752351992b83b368586fc84dca669a2679dfa7d6f5b1df3b33190f342222a8d`<br>`453d50f7a0df250776a0cab3d8b096aa194b49a57e88425ca87e46bf5521b542` |
| wallplugs | patchcore | 0.532097 | 0.579198 | 82.253 | 1577.554 | 837184499 | significant_higher_au_pro | `437a3d6f63e9ce551bc6710738cbaab22121f5b3bc592dace57dacfcec636d97`<br>`6ffd7c77dc95549ae174f324c19684a44a90808029672390c07cc72df9874972`<br>`e2517d5a507bf2a0da8e99af47a485fd88c0d900d4d8773966750afad8d7009f` |
| walnuts | patchcore | 0.716680 | 0.840926 | 119.591 | 2243.369 | 1186993139 | significant_higher_au_pro | `ac6584bb60bedf8a14ede6bc2c63ab0ed31ea150c5e14157465bafd6c9519975`<br>`459516eb474914946f90dd5a49a37aa9eba96d056e127ac4e029620fd63814d5`<br>`8dd81e382b9fc7fa7372bc3d71053a614b747e79f4845df477ea6825a1786372` |

## Seed-42 screening

| Family | Macro AU-PRO (95% CI) | Macro image AUROC (95% CI) | Run evidence |
| --- | ---: | ---: | --- |
| patchcore | 0.583867 [0.462450, 0.716594] | 0.732328 [0.639095, 0.823742] | `597dbe614d9aa98fd8939b0626aaf61def78fa4abac1b25755aeb5b5c980e81a`<br>`d6c6b6bbf7fec007b0f73ecea42bb6e0115d4bf105ba31619cc413454d58c8f3`<br>`7c7ed4bbdfdcbd94ae1d12ce240bb711efda00eb7cbe20ad821e7e9a6c0d220c`<br>`7179e031e1f41849866b581a0cc9261e5e3a598548359db93fc09d33e53ef3b5`<br>`fb22267b01354c9d534cbc322b239a1493c45b86936abb4cf0d917e2482c2ca4`<br>`8752351992b83b368586fc84dca669a2679dfa7d6f5b1df3b33190f342222a8d`<br>`6ffd7c77dc95549ae174f324c19684a44a90808029672390c07cc72df9874972`<br>`459516eb474914946f90dd5a49a37aa9eba96d056e127ac4e029620fd63814d5` |
| efficient_ad | 0.334067 [0.211450, 0.511882] | 0.630025 [0.551957, 0.723058] | `ec781513bd6a3affb2ca48cfca83ebcef2962c14c04e3b931ca1d00c3af2bc95`<br>`e4920f7c73fe684b600cd7acca24e3f4ae4950146c52cea6d7cdf24abae93a42`<br>`00c68e091a1352166e84f7d4c76a9d8e6e36c4a8f996ac0f82e7c8f302221f6a`<br>`29623b228ef46307275e9dfb2113a5f301c40039dceab607f2e124aac62a8d1b`<br>`7247ff893a9ecca0bce801753d3569923eac0ca737727a6ec43031ef6d1f3bef`<br>`647f89379a8c992a385f91bc97534199c7aa79c1f59400f3e4e021e4ccef0245`<br>`996cf010750e7d0296f02256f2b0bca5cd07097886084f94e1f9a5a8fc590672`<br>`e6e1231bef09ac7ed3059e71f31c42f2747d9f68540eac32af6ab23d190b1a41` |
| dinomaly | 0.586910 [0.453140, 0.722095] | 0.678175 [0.587780, 0.757432] | `fcc4b2c90275cd585b79adb1e33be05cfc18222d41af235dfcba22bab3016cd3`<br>`b96429546f4bb46d528156e305cee5efd18be8e1f96513ba615d867879572a1f`<br>`8a3b687e9da2e93e7f407aa0496cee17482302ce02faf1343e785e6d6e33bcde`<br>`d47baf7b7871fc45185753bee4a526ead9194847200612e48c241c2511aab726`<br>`fe366c4598620920e434af345569ffcd30941dd1621379249eb4e8a44d89cac7`<br>`792221b53b1231f5ce22c57c1b565c9efcb12a8e91f04eb85273b404ba05f69e`<br>`73f313cbf83ebf08a024f59720323763c63396fcea8710f27ed272c62ea8712a`<br>`8355aa5e398e1b9137b8615ec3cec99a09a2856b08b2f9d4c895429d9459aefb` |

## Limitations

- Public results selected contenders and category champions; private results have not selected or tuned them.
- GPU latency is batch-size-1 model execution on the recorded local CUDA environment; setup time is reported separately in JSON.
- Peak VRAM is the maximum allocated during the frozen public prediction run.
- CPU latency and official private/private-mixed results are not evaluated in this artifact.
