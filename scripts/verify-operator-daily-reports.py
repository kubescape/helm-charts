#!/usr/bin/env python3
"""Run published Operator images with rendered chart config and local HTTP fixtures.

Requires helm, podman, openssl and PyYAML. No Kubernetes cluster or cloud account
is used. The TLS proxy terminates version-check requests locally; it never
forwards traffic. This exercises the image's immediate daily report, not the
24-hour timer or deployment of the whole chart into Kubernetes.
"""
import argparse
import http.client
import http.server
import json
from pathlib import Path
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.request

import yaml


class Kubernetes(http.server.BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        if 'watch=true' in self.path:
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.flush()
            time.sleep(30)
            return
        if self.path.endswith('/services/kubernetes'):
            body = {'apiVersion': 'v1', 'kind': 'Service',
                    'metadata': {'name': 'kubernetes', 'uid': 'report-fixture'}}
        elif self.path.endswith('/nodes/report-fixture'):
            body = {'apiVersion': 'v1', 'kind': 'Node',
                    'metadata': {'name': 'report-fixture'}, 'spec': {}}
        else:
            body = {'apiVersion': 'v1', 'kind': 'List',
                    'metadata': {'resourceVersion': '1'}, 'items': []}
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())


class ReportProxy(http.server.BaseHTTPRequestHandler):
    reports = []
    tls = None

    def log_message(self, *_):
        pass

    def do_CONNECT(self):
        if self.path != 'version-check.ks-services.co:443':
            self.send_error(403)
            return
        self.send_response(200)
        self.end_headers()
        with self.tls.wrap_socket(self.connection, server_side=True) as conn:
            conn.settimeout(10)
            stream = conn.makefile('rb')
            request = stream.readline().decode().strip()
            headers = http.client.parse_headers(stream)
            body = json.loads(stream.read(int(headers.get('Content-Length', 0))))
            self.reports.append({'request': request, 'body': body})
            response = b'{"message":"local daily-report fixture accepted"}'
            conn.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n'
                         + f'Content-Length: {len(response)}\r\nConnection: close\r\n\r\n'.encode()
                         + response)
        self.close_connection = True


def run(*args):
    return subprocess.check_output(args, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', default='quay.io/kubescape/operator:v0.2.188')
    parser.add_argument('--seconds', type=int, default=20)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='operator-reports-') as tmp:
        folder = Path(tmp)
        folder.chmod(0o755)
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(folder / 'key.pem'), '-out', str(folder / 'cert.pem'),
                        '-days', '1', '-subj', '/CN=version-check.ks-services.co',
                        '-addext', 'subjectAltName=DNS:version-check.ks-services.co'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ReportProxy.tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ReportProxy.tls.load_cert_chain(folder / 'cert.pem', folder / 'key.pem')
        api = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Kubernetes)
        proxy = http.server.ThreadingHTTPServer(('127.0.0.1', 0), ReportProxy)
        for server in (api, proxy):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            print(run('podman', 'image', 'inspect', args.image, '--format',
                      '{{.Digest}}').strip(), flush=True)
            for case in ('online', 'offline', 'offline-conflict'):
                ReportProxy.reports = []
                values = {'clusterName': 'report-fixture',
                          'capabilities': {'continuousScan': 'disable',
                                           'vulnerabilityScan': 'disable',
                                           'configurationScan': 'enable',
                                           'relevancy': 'disable',
                                           'admissionController': 'disable',
                                           'kubescapeOffline': 'disable' if case == 'online' else 'enable'},
                          'nodeAgent': {'autoscaler': {'enabled': False}},
                          'operator': {'image': {'repository': args.image.rsplit(':', 1)[0],
                                                 'tag': args.image.rsplit(':', 1)[1]},
                                       'rulesUpdateConfig': {'enabled': False}},
                          'global': {'httpsProxy': f'http://127.0.0.1:{proxy.server_port}'}}
                if case == 'offline-conflict':
                    values['operator']['env'] = [{'name': 'KS_SKIP_UPDATE_CHECK', 'value': 'false'}]
                (folder / 'values.yaml').write_text(yaml.safe_dump(values))
                docs = list(yaml.safe_load_all(run('helm', 'template', 'reports',
                            str(root / 'charts/kubescape-operator'), '--kube-version', '1.28.0',
                            '-f', str(folder / 'values.yaml'))))
                deployment = next(d for d in docs if d and d.get('kind') == 'Deployment'
                                  and d['metadata']['name'] == 'operator')
                configmaps = {d['metadata']['name']: d['data'] for d in docs
                              if d and d.get('kind') == 'ConfigMap'}
                for volume in deployment['spec']['template']['spec']['volumes']:
                    if 'configMap' in volume:
                        configmap = volume['configMap']
                        for item in configmap.get('items', []):
                            (folder / item['path']).write_text(configmaps[configmap['name']][item['key']])
                (folder / 'kubeconfig').write_text(yaml.safe_dump({
                    'apiVersion': 'v1', 'kind': 'Config', 'current-context': 'fixture',
                    'clusters': [{'name': 'fixture', 'cluster': {'server': f'http://127.0.0.1:{api.server_port}'}}],
                    'contexts': [{'name': 'fixture', 'context': {'cluster': 'fixture', 'user': 'fixture'}}],
                    'users': [{'name': 'fixture', 'user': {}}]}))
                container = deployment['spec']['template']['spec']['containers'][0]
                assert container['image'] == args.image
                env = {e['name']: e['value'] for e in container['env'] if 'value' in e}
                env.update(KUBECONFIG='/etc/config/kubeconfig', NODE_NAME='report-fixture',
                           SSL_CERT_FILE='/etc/config/cert.pem', NO_PROXY='127.0.0.1,localhost',
                           no_proxy='127.0.0.1,localhost')
                cidfile = folder / 'container.cid'
                cidfile.unlink(missing_ok=True)
                cmd = ['podman', 'run', '--rm', '--cidfile', str(cidfile), '--network=host', '--security-opt=label=disable',
                       '-v', f'{folder}:/etc/config:ro']
                for key, value in env.items():
                    cmd += ['-e', f'{key}={value}']
                cmd += [args.image]
                print(case, json.dumps(env, sort_keys=True), flush=True)
                with (folder / 'operator.log').open('w') as log:
                    process = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, text=True)
                    ready = False
                    try:
                        time.sleep(args.seconds)
                        assert process.poll() is None, f'{case}: Operator exited before validation'
                        with urllib.request.urlopen('http://127.0.0.1:8000/v1/readiness', timeout=2) as response:
                            ready = response.status == 200
                    finally:
                        if cidfile.exists() and process.poll() is None:
                            subprocess.run(['podman', 'stop', '--time', '1', cidfile.read_text().strip()], check=True)
                        process.wait(timeout=15)
                output = (folder / 'operator.log').read_text()
                print(output, flush=True)
                reports = ReportProxy.reports
                print(case, json.dumps(reports), flush=True)
                assert ready, f'{case}: Operator never became ready'
                assert '"level":"fatal"' not in output
                assert 'Image version:' in output
                if case == 'online':
                    assert 'local daily-report fixture accepted' in output
                assert len(reports) == (1 if case == 'online' else 0), (case, reports)
                if reports:
                    assert reports[0]['request'] == 'POST / HTTP/1.1'
                    assert reports[0]['body']['context'] == 'daily-report'
                print(f'PASS {case}: ready={ready}, daily-report POSTs={len(reports)}', flush=True)
        finally:
            api.shutdown()
            proxy.shutdown()


if __name__ == '__main__':
    main()
