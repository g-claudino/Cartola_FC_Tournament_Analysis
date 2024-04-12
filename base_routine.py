
import pandas as pd
import class_api

with open('config.txt') as file:
    lines = [line.rstrip() for line in file]

auth_bearer = lines[0]
xglb_tag = lines[1]
slug = lines[2]
slug2 = lines[3]
api = class_api.API(xglb_tag, auth_bearer)

data_json = api.request_api(slug)
df_turno1 = pd.DataFrame(data_json)

data_json_geral = api.request_api(slug2)
df_geral = pd.DataFrame(data_json_geral['times'])

print(df_geral)

