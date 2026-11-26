# Resumen de experimentos

```
                     paso                   corrida status  videos  canales  tasa_base   auc  auc_std  auc_within  solo_texto  solo_formato  lift_at_10  segundos
                   0 base                   fábrica     ok    4772       76      0.301 0.510    0.024       0.528       0.514         0.501       1.027       4.7
 1 etiqueta: theta y modo                 theta=1.3     ok    4772       76      0.361 0.512    0.021       0.527       0.516         0.500       1.026       4.7
 1 etiqueta: theta y modo                 theta=2.0     ok    4772       76      0.204 0.512    0.034       0.523       0.531         0.496       1.014       5.2
 1 etiqueta: theta y modo           modo percentile     ok    4772       76      0.248 0.502    0.016       0.540       0.520         0.475       1.016       5.0
   2 etiqueta: linea base               method=bins     ok    4663       76      0.320 0.529    0.015       0.526       0.530         0.508       0.995       5.2
3 vocabulario por canales            min_channels=3     ok    4772       76      0.301 0.512    0.022       0.528       0.516         0.501       1.002       6.7
3 vocabulario por canales            min_channels=5     ok    4772       76      0.301 0.509    0.024       0.521       0.516         0.501       1.015       6.0
3 vocabulario por canales            min_channels=8     ok    4772       76      0.301 0.510    0.021       0.520       0.519         0.501       0.995       6.4
                  4 texto                  min_df=3     ok    4772       76      0.301 0.509    0.024       0.529       0.514         0.501       1.047       5.0
                  4 texto                 min_df=10     ok    4772       76      0.301 0.506    0.025       0.528       0.510         0.501       1.033       4.9
                  4 texto         max_features=5000     ok    4772       76      0.301 0.510    0.024       0.528       0.514         0.501       1.027       4.9
                  4 texto               char_ngrams     ok    4772       76      0.301 0.506    0.019       0.526       0.508         0.501       1.064      17.7
                 5 modelo                     C=0.1     ok    4772       76      0.301 0.505    0.031       0.515       0.516         0.503       1.048       4.5
                 5 modelo                     C=0.3     ok    4772       76      0.301 0.506    0.029       0.521       0.516         0.501       0.998       4.8
                 5 modelo                       C=3     ok    4772       76      0.301 0.510    0.020       0.529       0.511         0.500       1.022       5.2
                 5 modelo                      C=10     ok    4772       76      0.301 0.511    0.020       0.527       0.512         0.500       1.038       5.9
                 5 modelo     class_weight=balanced     ok    4772       76      0.301 0.510    0.023       0.529       0.513         0.500       1.019       5.4
                 5 modelo                penalty=l1     ok    4772       76      0.301 0.504    0.027       0.511       0.499         0.501       1.036      29.4
               6 recencia              vida media=7     ok    4772       76      0.301 0.491    0.039       0.501       0.496         0.493       0.902       5.2
               6 recencia             vida media=14     ok    4772       76      0.301 0.502    0.028       0.517       0.506         0.500       0.993       5.2
               6 recencia             vida media=45     ok    4772       76      0.301 0.522    0.020       0.541       0.523         0.500       1.112       5.3
               6 recencia             vida media=60     ok    4772       76      0.301 0.526    0.020       0.540       0.526         0.500       1.132       5.4
               6 recencia                  sin peso     ok    4772       76      0.301 0.538    0.025       0.539       0.536         0.501       1.283       5.4
                    final fábrica [semillas nuevas]     ok    4772       76      0.309 0.514    0.017       0.521       0.514         0.502       1.040       5.1
                    final   mejor [semillas nuevas]     ok    4772       76      0.309 0.524    0.019       0.535       0.521         0.506       1.098       5.5
                por nicho                   nicho 1     ok    1575       23      0.276 0.499    0.069       0.494       0.517         0.485       1.110       2.3
                por nicho                   nicho 3     ok    1268       19      0.329 0.559    0.053       0.547       0.520         0.578       1.054       1.7
                por nicho                   nicho 4     ok    1142       19      0.311 0.581    0.044       0.573       0.616         0.515       1.317       1.6
                por nicho                   nicho 5     ok     787       15      0.339 0.508    0.045       0.526       0.496         0.500       1.258       1.4
                     fuga  recomendada (barajado 1)     ok    4772       76      0.322 0.521    0.021       0.516       0.527         0.518       1.215       5.0
                     fuga  recomendada (barajado 2)     ok    4772       76      0.318 0.510    0.015       0.492       0.503         0.517       1.057       5.1
```

Configuración recomendada (best_config.json): `{"data": {"niche_ids": [1, 3, 4, 5]}, "weights": {"half_life_days": 45}}`
AUC con semillas nuevas: 0.524 ± 0.019
AUC con etiquetas barajadas: 0.516
Semáforo: ROJO: revisa fuga y etiqueta antes de seguir