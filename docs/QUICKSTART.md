# RoboOnto 0.9 快速上手

```sh
python3 -m pip install -e .
python3 -m pytest -q
```

迁移 X2：

```sh
roboonto pack migrate robots/agibot_x2 \
  -o robots/agibot_x2/agibot_x2.pack.yaml
roboonto pack validate robots/agibot_x2/agibot_x2.pack.yaml
roboonto pack inspect robots/agibot_x2/agibot_x2.pack.yaml
```

直接导入 URDF：

```sh
roboonto import urdf robot.urdf \
  --robot-id my_robot \
  -o my_robot.pack.yaml
```

直接导入 SDK：

```sh
roboonto import sdk-code /path/to/sdk/src \
  --robot-id my_robot \
  -o my_robot.sdk.pack.yaml
```

架构与限制见 [README](../README.md)、[PackModule 规范](PACKMODULE_0.9_SPEC.md)
和 [3.0 集成契约](ROBOONTO3_INTEGRATION.md)。
