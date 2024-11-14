from ..blueprint import create_a3_mega_blueprint
import ruamel.yaml

from xpk.core import blueprint

yaml = ruamel.yaml.YAML()

yaml.register_class(blueprint.CtkBlueprint)

a3_yaml_test_path = "src/xpk/core/tests/data/a3_mega.yaml"


def test_create_a3_mega_blueprint():
  ctk_test = create_a3_mega_blueprint(
      project_id="foo",
      deployment_name="xpk-gke-a3-megagpu",
      region="us-central1",
      zone="us-central1-c",
      auth_cidr="10.0.0.0/32",
  )
  with open(a3_yaml_test_path) as stream:
    ctk_yaml = yaml.load(stream)
    assert ctk_yaml.blueprint_name == ctk_test.blueprint_name
    assert ctk_yaml.vars == ctk_test.vars
    assert ctk_test.deployment_groups == ctk_yaml.deployment_groups
