#!/usr/bin/env python
# -*- python -*-
# -*- coding: utf-8 -*-

from __future__ import print_function

# Generic imports
import argparse
import pytz
import ssl
import sys
import urlparse

from datetime import datetime
from yamlconfig import YamlConfig

from BaseHTTPServer import BaseHTTPRequestHandler
from BaseHTTPServer import HTTPServer
from SocketServer import ForkingMixIn

# VMWare specific imports
from pyVmomi import vim, vmodl
from pyVim import connect

# Prometheus specific imports
from prometheus_client.core import GaugeMetricFamily, _floatToGoString
from prometheus_client import CONTENT_TYPE_LATEST

class ForkingHTTPServer(ForkingMixIn, HTTPServer):
    pass

class VMWareMetricsHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        BaseHTTPRequestHandler.__init__(self, *args, **kwargs)

    def do_GET(self):
        import pdb; pdb.set_trace()
        try:
            self.config = YamlConfig(args.config_file)
            if 'default' not in self.config.keys():
                print("Error, you must have a default section in config file")
                exit(1)
        except:
            raise SystemExit("Error, cannot read configuration file")

        url = urlparse.urlparse(self.path)
        if url.path == '/metrics':
            self.generate_latest_target(url)
        elif url.path == '/healthz':
            self.send_response(200)
            self.end_headers()
            self.wfile.write('Server is UP'.encode())
        elif url.path == '/':
            self.send_response(200)
            self.end_headers()
            self.wfile.write("""<html>
            <head><title>VMWare Exporter</title></head>
            <body>
            <h1>VMWare Exporter</h1>
            <p>Visit <code>/metrics</code> to use.</p>
            </body>
            </html>""")
        else:
            self.send_response(404)
            self.end_headers()

    def generate_latest_target(self, url):
        params = urlparse.parse_qs(url.query)
        if 'target' not in params:
            self.send_response(400)
            self.end_headers()
            self.wfile.write("Missing 'target' from parameters")
            return
        target = params.get('target')[0]
        section = params.get("section", ["default"])[0]

        output = []
        for metric in self.collect(target, section):
            output.append('# HELP {0} {1}'.format(
                metric.name, metric.documentation.replace('\\', r'\\').replace('\n', r'\n')))
            output.append('\n# TYPE {0} {1}\n'.format(metric.name, metric.type))
            for name, labels, value in metric.samples:
                if labels:
                    labelstr = '{{{0}}}'.format(','.join(
                        ['{0}="{1}"'.format(
                         k, v.replace('\\', r'\\').replace('\n', r'\n').replace('"', r'\"'))
                         for k, v in sorted(labels.items())]))
                else:
                    labelstr = ''
                output.append('{0}{1} {2}\n'.format(name, labelstr, _floatToGoString(value)))
        if output != []:
            self.send_response(200)
            self.send_header('Content-Type', CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(''.join(output).encode('utf-8'))
        else:
            self.send_response(500)
            self.end_headers()
            self.wfile.write('cannot connect to vmware')


    def collect(self, target=None, section='default'):
        if section not in self.config.keys():
            print("{} is not a valid section, using default".format(section))
            section='default'
        metrics = {
                    'vmware_vm_power_state': GaugeMetricFamily(
                        'vmware_vm_power_state',
                        'VMWare VM Power state (On / Off)',
                        labels=['vm_name']),
                    'vmware_vm_boot_timestamp_seconds': GaugeMetricFamily(
                        'vmware_vm_boot_timestamp_seconds',
                        'VMWare VM boot time in seconds',
                        labels=['vm_name']),
                    'vmware_vm_snapshots': GaugeMetricFamily(
                        'vmware_vm_snapshots',
                        'VMWare current number of existing snapshots',
                        labels=['vm_name']),
                    'vmware_vm_snapshot_timestamp_seconds': GaugeMetricFamily(
                        'vmware_vm_snapshot_timestamp_seconds',
                        'VMWare Snapshot creation time in seconds',
                        labels=['vm_name', 'vm_snapshot_name']),
                    'vmware_vm_num_cpu': GaugeMetricFamily(
                        'vmware_vm_num_cpu',
                        'VMWare Number of processors in the virtual machine',
                        labels=['vm_name']),
                    'vmware_datastore_capacity_size': GaugeMetricFamily(
                        'vmware_datastore_capacity_size',
                        'VMWare Datasore capacity in bytes',
                        labels=['ds_name']),
                    'vmware_datastore_freespace_size': GaugeMetricFamily(
                        'vmware_datastore_freespace_size',
                        'VMWare Datastore freespace in bytes',
                        labels=['ds_name']),
                    'vmware_datastore_uncommited_size': GaugeMetricFamily(
                        'vmware_datastore_uncommited_size',
                        'VMWare Datastore uncommitted in bytes',
                        labels=['ds_name']),
                    'vmware_datastore_provisoned_size': GaugeMetricFamily(
                        'vmware_datastore_provisoned_size',
                        'VMWare Datastore provisoned in bytes',
                        labels=['ds_name']),
                    'vmware_datastore_hosts': GaugeMetricFamily(
                        'vmware_datastore_hosts',
                        'VMWare Hosts number using this datastore',
                        labels=['ds_name']),
                    'vmware_datastore_vms': GaugeMetricFamily(
                        'vmware_datastore_vms',
                        'VMWare Virtual Machines number using this datastore',
                        labels=['ds_name']),
                    'vmware_host_power_state': GaugeMetricFamily(
                        'vmware_host_power_state',
                        'VMWare Host Power state (On / Off)',
                        labels=['host_name']),
                    'vmware_host_boot_timestamp_seconds': GaugeMetricFamily(
                        'vmware_host_boot_timestamp_seconds',
                        'VMWare Host boot time in seconds',
                        labels=['host_name']),
                    'vmware_host_cpu_usage': GaugeMetricFamily(
                        'vmware_host_cpu_usage',
                        'VMWare Host CPU usage in Mhz',
                        labels=['host_name']),
                    'vmware_host_cpu_max': GaugeMetricFamily(
                        'vmware_host_cpu_max',
                        'VMWare Host CPU max availability in Mhz',
                        labels=['host_name']),
                    'vmware_host_memory_usage': GaugeMetricFamily(
                        'vmware_host_memory_usage',
                        'VMWare Host Memory usage in Mbytes',
                        labels=['host_name']),
                    'vmware_host_memory_max': GaugeMetricFamily(
                        'vmware_host_memory_max',
                        'VMWare Host Memory Max availability in Mbytes',
                        labels=['host_name']),
                }

        print("[{0}] Start collecting vcenter metrics for {1}".format(datetime.utcnow().replace(tzinfo=pytz.utc), target))

        self.si = self._vmware_connect(target, section)
        if not self.si:
           print("Error, cannot connect to vmware")
           return

        content = self.si.RetrieveContent()

        # Get performance metrics counter information
        counter_info = self._vmware_perf_metrics(content)

        # Fill Snapshots (count and age)
        vm_counts, vm_ages = self._vmware_get_snapshots(content)
        for v in vm_counts:
            metrics['vmware_vm_snapshots'].add_metric([v['vm_name']],
                                                            v['snapshot_count'])
        for vm_age in vm_ages:
            for v in vm_age:
                metrics['vmware_vm_snapshot_timestamp_seconds'].add_metric([v['vm_name'],
                                        v['vm_snapshot_name']],
                                        v['vm_snapshot_timestamp_seconds'])

        # Fill Datastore
        self._vmware_get_datastores(content, metrics)

        # Fill VM Informations
        self._vmware_get_vms(content, metrics, counter_info)

        # Fill Hosts Informations
        self._vmware_get_hosts(content, metrics)

        print("[{0}] Stop collecting vcenter metrics for {1}".format(datetime.utcnow().replace(tzinfo=pytz.utc), target))

        self._vmware_disconnect()

        for metricname, metric in metrics.items():
            yield metric




    def _to_unix_timestamp(self, my_date):
        return ((my_date - datetime(1970,1,1,tzinfo=pytz.utc)).total_seconds())


    def _vmware_get_obj(self, content, vimtype, name=None):
        """
         Get the vsphere object associated with a given text name
        """
        obj = None
        container = content.viewManager.CreateContainerView(
            content.rootFolder, vimtype, True)
        if name:
            for c in container.view:
                if c.name == name:
                    obj = c
                    return [obj]
        else:
            return container.view


    def _vmware_connect(self, target, section):
        """
        Connect to Vcenter and get connection
        """

        context = None
        if self.config[section]['ignore_ssl'] and \
                hasattr(ssl, "_create_unverified_context"):
            context = ssl._create_unverified_context()

        try:
            si = connect.Connect(target, 443,
                                 self.config[section]['vmware_user'],
                                 self.config[section]['vmware_password'],
                                 sslContext=context)

            return si

        except vmodl.MethodFault as error:
            print("Caught vmodl fault: " + error.msg)
            return None

    def _vmware_disconnect(self):
        """
        Disconnect from Vcenter
        """
        connect.Disconnect(self.si)

    def _vmware_perf_metrics(self, content):
        # create a mapping from performance stats to their counterIDs
        # counter_info: [performance stat => counterId]
        # performance stat example: cpu.usagemhz.LATEST
        counter_info = {}
        for c in content.perfManager.perfCounter:
            prefix = c.groupInfo.key
            counter_full = "{}.{}.{}".format(c.groupInfo.key,
                                                    c.nameInfo.key,c.rollupType)
            counter_info[counter_full] = c.key
        return counter_info


    def _vmware_list_snapshots_recursively(self, snapshots):
        """
        Get snapshots from a VM list, recursively
        """
        snapshot_data = []
        for snapshot in snapshots:
            snap_timestamp = self._to_unix_timestamp(snapshot.createTime)
            snap_info = {
                            'vm_snapshot_name': snapshot.name,
                            'vm_snapshot_timestamp_seconds': snap_timestamp
                        }
            snapshot_data.append(snap_info)
            snapshot_data = snapshot_data + self._vmware_list_snapshots_recursively(
                                            snapshot.childSnapshotList)
        return snapshot_data


    def _vmware_get_snapshots(self, content):
        """
        Get snapshots from all VM
        """
        snapshots_count_table = []
        snapshots_age_table = []
        for vm in self._vmware_get_obj(content, [vim.VirtualMachine]):

            if not vm or vm.snapshot is None:
                continue

            else:
                snapshot_paths = self._vmware_list_snapshots_recursively(
                                    vm.snapshot.rootSnapshotList)
                for sn in snapshot_paths:
                    sn['vm_name'] = vm.name
                # Add Snapshot count per VM
                snapshot_count = len(snapshot_paths)
                snapshot_count_info = {
                    'vm_name': vm.name,
                    'snapshot_count': snapshot_count
                }
                snapshots_count_table.append(snapshot_count_info)
            snapshots_age_table.append(snapshot_paths)
        return snapshots_count_table, snapshots_age_table


    def _vmware_get_datastores(self, content, ds_metrics):
        """
        Get Datastore information
        """
        for ds in self._vmware_get_obj(content, [vim.Datastore]):
            #ds.RefreshDatastoreStorageInfo()
            summary = ds.summary
            ds_capacity = summary.capacity
            ds_freespace = summary.freeSpace
            ds_uncommitted = summary.uncommitted if summary.uncommitted else 0
            ds_provisioned = ds_capacity - ds_freespace + ds_uncommitted

            ds_metrics['vmware_datastore_capacity_size'].add_metric([summary.name], ds_capacity)
            ds_metrics['vmware_datastore_freespace_size'].add_metric([summary.name], ds_freespace)
            ds_metrics['vmware_datastore_uncommited_size'].add_metric([summary.name], ds_uncommitted)
            ds_metrics['vmware_datastore_provisoned_size'].add_metric([summary.name], ds_provisioned)
            ds_metrics['vmware_datastore_hosts'].add_metric([summary.name], len(ds.host))
            ds_metrics['vmware_datastore_vms'].add_metric([summary.name], len(ds.vm))


    def _vmware_get_vms(self, content, vm_metrics, counter_info):
        """
        Get VM information
        """

        # List of performance counter we want
        perf_list = [
            'cpu.ready.summation',
            'cpu.usage.average',
            'cpu.usagemhz.average',
            'disk.usage.average',
            'disk.read.average',
            'disk.write.average',
            'mem.usage.average',
            'net.received.average',
            'net.transmitted.average',
            ]

        # Prepare gauges
        for p in perf_list:
            p_metric = 'vmware_vm_' + p.replace('.', '_')
            vm_metrics[p_metric] = GaugeMetricFamily(
                                            p_metric,
                                            p_metric,
                                            labels=['vm_name'])

        for vm in self._vmware_get_obj(content, [vim.VirtualMachine]):
            summary = vm.summary

            power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
            num_cpu = summary.config.numCpu
            vm_metrics['vmware_vm_power_state'].add_metric([vm.name], power_state)
            vm_metrics['vmware_vm_num_cpu'].add_metric([vm.name], num_cpu)

            # Get metrics for poweredOn vms only
            if power_state:
                if summary.runtime.bootTime:
                    vm_metrics['vmware_vm_boot_timestamp_seconds'].add_metric([vm.name],
                            self._to_unix_timestamp(summary.runtime.bootTime))

                for p in perf_list:
                    p_metric = 'vmware_vm_' + p.replace('.', '_')
                    counter_key = counter_info[p]
                    metric_id = vim.PerformanceManager.MetricId(
                                                        counterId=counter_key,
                                                        instance='')
                    spec = vim.PerformanceManager.QuerySpec(
                                                        maxSample=1,
                                                        entity=vm,
                                                        metricId=[metric_id],
                                                        intervalId=20)
                    result = content.perfManager.QueryStats(querySpec=[spec])
                    try:
                        vm_metrics[p_metric].add_metric([vm.name],
                                        float(sum(result[0].value[0].value)))
                    except:
                        print("Error, cannot get vm metrics {0} for {1}".format(p_metric, vm.name))
                        pass



    def _vmware_get_hosts(self, content, host_metrics):
        """
        Get Host (ESXi) information
        """
        for host in self._vmware_get_obj(content, [vim.HostSystem]):
            summary = host.summary

            # Power state
            power_state = 1 if summary.runtime.powerState == 'poweredOn' else 0
            host_metrics['vmware_host_power_state'].add_metric([host.name], power_state)

            if power_state:
                # Uptime
                if summary.runtime.bootTime:
                    host_metrics['vmware_host_boot_timestamp_seconds'].add_metric([host.name],
                            self._to_unix_timestamp(summary.runtime.bootTime))

                # CPU Usage (in Mhz)
                host_metrics['vmware_host_cpu_usage'].add_metric([host.name],
                                        summary.quickStats.overallCpuUsage)
                cpu_core_num = summary.hardware.numCpuCores
                cpu_total = summary.hardware.cpuMhz * cpu_core_num
                host_metrics['vmware_host_cpu_max'].add_metric([host.name], cpu_total)

                # Memory Usage (in Mhz)
                host_metrics['vmware_host_memory_usage'].add_metric([host.name],
                                        summary.quickStats.overallMemoryUsage)
                host_metrics['vmware_host_memory_max'].add_metric([host.name],
                            float(summary.hardware.memorySize) / 1024 / 1024)


if __name__ == '__main__':
    reload(sys)
    sys.setdefaultencoding("utf-8")

    parser = argparse.ArgumentParser(description='VMWare metrics exporter for Prometheus')
    parser.add_argument('-c', '--config', dest='config_file',
                        default='config.yml', help="configuration file")
    parser.add_argument('-p', '--port', dest='port', type=int,
                        default=9272, help="HTTP port to expose metrics")

    args = parser.parse_args()

    try:

        print("Starting web server on port {}".format(args.port))

        server = ForkingHTTPServer(('', args.port), VMWareMetricsHandler)
        server.serve_forever()
    except KeyboardInterrupt:
        print(" Interrupted")
        exit(0)
