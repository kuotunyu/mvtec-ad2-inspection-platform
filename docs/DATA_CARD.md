# MVTec AD 2 Data Card

## Source and identity

The project uses the official `mvtec_ad_2.tar.gz` archive published by MVTec. The approved acquisition contract records:

```text
Archive bytes: 32,739,596,982
Archive SHA-256: c0ded99ef32bfc8e352d52beb44515e5b292b8598cb963aadfa91ca0763505e4
Frozen dataset-manifest SHA-256: 557fd46fcfaa1c2618be315bced7f9f0ba381d8f45119929a200a9d12d1895bf
```

The archive, extracted files, masks, and derived private material are retained outside Git and are not redistributed. Obtain the dataset from the [official MVTec AD 2 page](https://www.mvtec.com/research-teaching/datasets/mvtec-ad-2) and accept its terms directly.

## License

The dataset is licensed CC BY-NC-SA 4.0. That license is separate from the repository's source-code license. Training on this dataset does not establish commercial deployment rights for resulting artifacts.

## Categories and splits

The dataset contains `can`, `fabric`, `fruit_jelly`, `rice`, `sheet_metal`, `vial`, `wallplugs`, and `walnuts`.

- `train/good` is used only for fitting.
- Public images and masks are used for metric evaluation, contender selection, and champion freezing.
- Private and private-mixed inputs are used only after freezing for the official private boundary.
- Private labels are never used for tuning.

## Public fixtures

Files under `fixtures/public-demo` are deterministic geometric images created by this project. Their seeds, hashes, intended mock outcomes, generator version, and CC0 project-generated status are recorded in the fixture manifest. They contain no source or texture from MVTec and are the only inspection images permitted in source, CI, screenshots, and the CPU demo.
