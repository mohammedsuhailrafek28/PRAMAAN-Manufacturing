# Dataset attribution

Steel Plates Faults. Buscema, M., Terzi, S., & Tastle, W. (2010). UCI Machine Learning Repository. https://doi.org/10.24432/C5J88N
Licence: Creative Commons Attribution 4.0 International (CC BY 4.0). https://archive.ics.uci.edu/dataset/198/steel+plates+faults

`ml/data/Faults.NNA` and `ml/data/Faults27x7_var` are the unchanged files from `steel+plates+faults.zip` (zip sha-256 cb8eb9859198b63f053e443513036b401746fa517ef58bd17c846c6741c93919; Faults.NNA sha-256 08994f5b0185a8e6cc22afe9910fd36834990fb1ca30852ed79012a832fbff55).
`ml/data/heldout.csv` and `public/ml/samples.json` are rows of that file (the 20% held out from training) with the dataset's own labels.

The reference project github.com/SabareeswaranC/steel-plate-fault-classification states no licence and ships pickled `.joblib` models. Nothing from it (code or model) is copied or executed here; the model is trained by `ml/train.mjs` from the UCI files above. Reproduce: `npm run ml:train` (deterministic, seed 42) then `npm run test:ml`.
