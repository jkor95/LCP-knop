"""Controleer de bestaande worker zonder hem uit te voeren of geheimen te tonen."""
import argparse
import ast
import json
from pathlib import Path


def inspect_launcher(path, worker):
    """Herken de aangetroffen DPAPI-starter zonder hem te importeren."""
    path, worker = Path(path), Path(worker)
    if path.name != 'account.py' or path.parent.name != 'support' or worker != path.with_name('upstream_worker.py'):
        raise ValueError('De Opstarten-installatie heeft een andere indeling. Er is niets vervangen.')
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    function = next((node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'worker'), None)
    if function is None:
        raise ValueError('De beveiligde workerstarter is niet herkend. Er is niets vervangen.')
    nodes = list(ast.walk(function))
    strings = {node.value for node in nodes if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    calls = [node for node in nodes if isinstance(node, ast.Call)]
    environment = any(isinstance(node.func, ast.Attribute) and ast.unparse(node.func) == 'os.environ.update'
                      and {'LCP_EMAIL', 'LCP_PASSWORD', 'LCP_PUBLISHABLE_KEY'}.issubset({kw.arg for kw in node.keywords}) for node in calls)
    loader = any(isinstance(node.func, ast.Attribute) and ast.unparse(node.func) == 'importlib.util.spec_from_file_location'
                 and len(node.args) >= 2 and ast.unparse(node.args[1]) == "ROOT / 'support' / 'upstream_worker.py'" for node in calls)
    local = any(isinstance(node, ast.ClassDef) and any(ast.unparse(base) == 'impl.LCPWorker' for base in node.bases) for node in nodes)
    mqtt_auth = any(isinstance(node.func, ast.Attribute) and ast.unparse(node.func) == 'w.client.username_pw_set' for node in calls)
    if not (environment and loader and local and mqtt_auth and 'upstream_worker.py' in strings):
        raise ValueError('De beveiligde workerstarter wijkt af. Er is niets vervangen.')


def inspect_worker(path, launcher_manages_mqtt=False):
    tree = ast.parse(Path(path).read_text(encoding='utf-8-sig'))
    strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    imports = {node.name for item in ast.walk(tree) if isinstance(item, ast.Import) for node in item.names}
    if not {'LCP_EMAIL', 'LCP_PASSWORD', 'LCP_PUBLISHABLE_KEY'}.issubset(strings) or 'paho.mqtt.client' not in imports:
        raise ValueError('De bestaande worker gebruikt een andere inlog- of MQTT-methode. Er is niets vervangen. Laat de installatiemap eerst controleren.')
    if strings.intersection({'3.0.0', '3.1.0', '3.2.0'}) and '/rest/v1/rpc/lcp_emit_sensor_event' in strings:
        config = Path(path).with_name('lcp_sensor_runtime.json')
        existing = json.loads(config.read_text(encoding='utf-8-sig')) if config.exists() else {}
        result = {key: existing.get(key, default) for key, default in [('mqtt_host','127.0.0.1'),('mqtt_port',1883),('topic_prefix','zigbee2mqtt/')]}
        if not isinstance(result['mqtt_host'], str) or not isinstance(result['mqtt_port'], int) or not isinstance(result['topic_prefix'], str):
            raise ValueError('De bestaande sensor-runtime heeft ongeldige MQTT-instellingen. Er is niets vervangen.')
        return result
    allowed = {'MQTT_HOST': 'mqtt_host', 'MQTT_PORT': 'mqtt_port', 'TOPIC_PREFIX': 'topic_prefix', 'MQTT_BASE_TOPIC': 'topic_prefix', 'BASE_TOPIC': 'topic_prefix'}
    result = {'mqtt_host': '127.0.0.1', 'mqtt_port': 1883, 'topic_prefix': 'zigbee2mqtt/'}
    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue
        for target in statement.targets:
            if isinstance(target, ast.Name) and target.id in allowed:
                try:
                    value = ast.literal_eval(statement.value)
                except (ValueError, TypeError):
                    raise ValueError('De MQTT-instellingen zijn dynamisch. De update stopt om de bestaande verbinding te behouden.') from None
                result[allowed[target.id]] = value
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr in ('connect', 'connect_async') and node.args:
            try:
                host = ast.literal_eval(node.args[0])
                port = ast.literal_eval(node.args[1]) if len(node.args) > 1 else 1883
            except (ValueError, TypeError):
                if not isinstance(node.args[0], ast.Name) or node.args[0].id != 'MQTT_HOST':
                    raise ValueError('De bestaande MQTT-verbinding is niet eenduidig herkenbaar. Er is niets vervangen.') from None
            else:
                result.update(mqtt_host=host, mqtt_port=port)
        constructor_auth = launcher_manages_mqtt and node.func.attr == 'username_pw_set' and any(
            node in ast.walk(method) for cls in tree.body if isinstance(cls, ast.ClassDef) and cls.name == 'LCPWorker'
            for method in cls.body if isinstance(method, ast.FunctionDef) and method.name == '__init__')
        if node.func.attr in ('tls_set', 'tls_set_context', 'tls_insecure_set', 'username_pw_set') and not constructor_auth:
            raise ValueError('De bestaande MQTT-verbinding gebruikt aanvullende beveiligingsinstellingen. Laat die eerst overnemen; er is niets vervangen.')
    if not isinstance(result['mqtt_host'], str) or not isinstance(result['mqtt_port'], int) or not isinstance(result['topic_prefix'], str):
        raise ValueError('De bestaande MQTT-instellingen zijn ongeldig. Er is niets vervangen.')
    result['topic_prefix'] = result['topic_prefix'].rstrip('/') + '/'
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--worker', required=True)
    parser.add_argument('--install-dir', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--launcher')
    args = parser.parse_args()
    try:
        if args.launcher:
            inspect_launcher(args.launcher, args.worker)
        result = inspect_worker(args.worker, launcher_manages_mqtt=bool(args.launcher))
        root = Path(args.install_dir)
        result.update(state_file=str(root/'sensor_state_v3.json'), health_file=str(root/'sensor_worker_health.json'))
        if args.launcher:
            result['launcher_state_isolated'] = True
        Path(args.output).write_text(json.dumps(result), encoding='utf-8')
        print('Bestaande inlogmethode en MQTT-verbinding herkend; instellingen blijven behouden.')
    except (ValueError, OSError, SyntaxError) as error:
        # Geen bronregels of overige exceptiondetails: oude scripts kunnen geheimen bevatten.
        print(str(error) if isinstance(error, ValueError) and not isinstance(error, SyntaxError) else 'De bestaande worker kon niet veilig worden gecontroleerd.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
