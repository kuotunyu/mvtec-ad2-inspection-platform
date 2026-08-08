# MVTec AD 2 Data Card

## Source and license

The project uses the official MVTec AD 2 archive from [MVTec](https://www.mvtec.com/research-teaching/datasets/mvtec-ad-2), licensed CC BY-NC-SA 4.0. The archive is acquired and retained outside this repository; it is not redistributed here.

- Official archive URL: `https://www.mydrive.ch/shares/150997/701c90d3aea6588f404936e32a674602/download/466712769-1743429042/mvtec_ad_2.tar.gz`
- Frozen dataset-manifest SHA-256: `557fd46fcfaa1c2618be315bced7f9f0ba381d8f45119929a200a9d12d1895bf`

## Layout and use

The eight categories are `can`, `fabric`, `fruit_jelly`, `rice`, `sheet_metal`, `vial`, `wallplugs`, and `walnuts`. Public images and masks are used for evaluation and model selection; private and private-mixed images are used only for the frozen private boundary check. No private labels are used for tuning.

The data contains industrial product imagery and binary anomaly masks. Results are research/non-commercial portfolio evidence and do not establish commercial deployment rights for the data or trained models.
