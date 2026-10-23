"""Controleer de bestaande worker zonder hem uit te voeren of geheimen te tonen."""
import argparse
import ast
import json
from pathlib import Path


def inspect_worker(path):
    tree = ast.parse(Path(path).read_text(encoding='utf-8-sig'))
    strings = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    imports = {node.name for item in ast.walk(tree) if isinstance(item, ast.Import) for node in item.names}
    if not {'LCP_EMAIL', 'LCP_PASSWORD', 'LCP_PUBLISHABLE_KEY'}.issubset(strings) or 'paho.mqtt.client' not in imports:
        raise ValueError('De bestaande worker gebruikt een andere inlog- of MQTT-methode. Er is niets vervangen. Laat de installatiemap eerst controleren.')
    if '3.0.0' in strings and '/rest/v1/rpc/lcp_emit_sensor_event' in strings:
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
        if node.func.attr in ('tls_set', 'tls_set_context', 'tls_insecure_set', 'username_pw_set'):
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
    args = parser.parse_args()
    try:
        result = inspect_worker(args.worker)
        root = Path(args.install_dir)
        result.update(state_file=str(root/'sensor_state_v3.json'), health_file=str(root/'sensor_worker_health.json'))
        Path(args.output).write_text(json.dumps(result), encoding='utf-8')
        print('Bestaande inlogmethode en MQTT-verbinding herkend; instellingen blijven behouden.')
    except (ValueError, OSError, SyntaxError) as error:
        # Geen bronregels of overige exceptiondetails: oude scripts kunnen geheimen bevatten.
        print(str(error) if isinstance(error, ValueError) and not isinstance(error, SyntaxError) else 'De bestaande worker kon niet veilig worden gecontroleerd.')
        raise SystemExit(1)


if __name__ == '__main__':
    main()
