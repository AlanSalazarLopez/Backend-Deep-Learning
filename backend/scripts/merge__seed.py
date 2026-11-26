import pandas as pd
a = pd.read_csv("data/channels_seed_v1.csv")
b = pd.read_csv("data/channels_seed_extra.csv")
m = pd.concat([a, b]).drop_duplicates("channel_id")
m.to_csv("data/channels_seed.csv", index=False)
print(m.groupby("niche_slug").size())