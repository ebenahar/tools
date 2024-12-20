from __future__ import print_function
import os
import re
import ssl
import sys
import requests
import atexit
import smtplib
import tempfile
import json
from subprocess import check_output
import smtplib
import datetime
import importlib
import argparse
from subprocess import check_output
from collections import defaultdict
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from ipdb import set_trace

from azure.common.credentials import ServicePrincipalCredentials
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient


from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage
from email.headerregistry import Address
from email.mime.text import MIMEText
from termcolor import colored
from prettytable import PrettyTable
from pyVim import connect
from pyVmomi import vim
from pyVim.connect import Disconnect, SmartStubAdapter, VimSessionOrientedStub


# vSphere details
BASE_VSPHERE_ENV_DICT = {
    "host": "",
    "username": "",
    "password": "",
    "port": 443,
    "cluster_name": '',
    "dc_name": '',
    "datastore": '',
    "lockable_resources_num": None
}

VCENTER7 = ""

VSPHERE7_CP_ENV_DICT = BASE_VSPHERE_ENV_DICT.copy()
VSPHERE7_CP_ENV_DICT.update({"host": VCENTER7, "lockable_resources_num": ''})

VSPHERE6_ECO_ENV_DICT = BASE_VSPHERE_ENV_DICT.copy()
VSPHERE6_ECO_ENV_DICT.update({"host": VCENTER7, "dc_name": '', "lockable_resources_num": ''})

VSPHERE7_LONG_ENV_DICT = BASE_VSPHERE_ENV_DICT.copy()
VSPHERE7_LONG_ENV_DICT.update({"host": VCENTER7, "dc_name": '', "lockable_resources_num": ''})

VSPHERE7_RDR_ENV_DICT = BASE_VSPHERE_ENV_DICT.copy()
VSPHERE7_RDR_ENV_DICT.update({"host": VCENTER7, "dc_name": '', "lockable_resources_num": ''})

VSPHERE7_MDR_ENV_DICT = BASE_VSPHERE_ENV_DICT.copy()
VSPHERE7_MDR_ENV_DICT.update({"host": VCENTER7, "dc_name": '', "lockable_resources_num": ''})


VSPHERE_ENV_DICT_LIST = [VSPHERE7_CP_ENV_DICT, VSPHERE6_ECO_ENV_DICT, VSPHERE7_LONG_ENV_DICT, VSPHERE7_RDR_ENV_DICT, VSPHERE7_MDR_ENV_DICT]



IPI_HINT = 'master-'
UPI_HINT = 'lb-'

HIGH_RUN_TIME = 120
HIGH_STORAGE = 3
HIGH_MEMORY = 35

# AWS details
AWS_CLOUDFORMATION_TAG = "aws:cloudformation:stack-name"
AWS_ENV_DICT = {"region_name": ""}

# Azure details
AZURE_DICT = {
    "account": "",
    "subscription_id": "",
    "tenant_id": "",
    "client_id": "",
    "client_secret": "",
    "cluster_resource_group": ""
}

IBM_CLOUD_DICT_EAST = {
    "account_id": "",
    "api_key": "",
    "region": ""
}

IBM_CLOUD_DICT_SOUTH = {
    "account_id": "",
    "api_key": "",
    "region": ""
}

IBM_CLOUD_DICTS = [IBM_CLOUD_DICT_EAST]


GCP_PROJECT_ID = ""


# Other
DIVIDER_STR = "-" * 75

# Email details
EMAIL_SENDER_USERNAME = ''
EMAIL_SENDER_PASSWORD = ''
TO_LIST = []
SMTP_DETAILS = smtplib.SMTP("smtp.gmail.com", 587)

IGNORE_LIST = ["rhcos", "rhel", "vCLS"]
MAIL_SUFFIX = "@redhat.com"

sslContext = ssl._create_unverified_context()
HEADER = '\033[95m'

SHEET_NAME = "DCs Utilization"


def remove_ocsci_dir():
    cmd = 'rm -rf ocs-ci'
    check_output(cmd, shell=True).decode()


def clone_ocsci():
    cmd = 'git clone https://github.com/red-hat-storage/ocs-ci.git'
    check_output(cmd, shell=True).decode()
    ocs_ci_path = f"{sys.path[0]}/ocs-ci"
    sys.path.append(ocs_ci_path)
    print(ocs_ci_path)
    os.chdir(ocs_ci_path)

path = sys.path[0]
sys.path.append("/home/elad/python_projects/ocs-ci")



class OpsBase:
    """
    """
    def get_resource_consumption_report(self):
        pass

    def get_cluster_name_prefix(self, parts, index=0):
        prefix = parts[index]
        return re.sub(r'[0-9]', '', prefix)

    def get_cluster_details(self):
        pass

    def set_table(self, table, run_times=None):
        table = table.get_html_string(
            attributes={
                'border': '1',
                'style': 'border-width: 1px; border-collapse: collapse; text-align: center; padding: 2px;'
            }
        )
        if run_times:
            for run_time in run_times:

                if run_time > HIGH_RUN_TIME:
                    run_time_str = f"{run_time} H"
                    red_color = '#FF0000'
                    table = re.sub(f'<td>{run_time_str}</td>', f'<td bgcolor="{red_color}">{run_time_str}</td>', table)

        return table


class VsphereOps(OpsBase):
    """
    """
    def __init__(self):
        super(VsphereOps, self).__init__()
        

    def set_env_details(self, env_dict):
        """

        """
        self.host = env_dict["host"]
        self.username = env_dict["username"]
        self.password = env_dict["password"]
        self.port = env_dict["port"]
        self.dc_name = env_dict["dc_name"]
        self.cluster_name = env_dict["cluster_name"]
        self.datastore = env_dict["datastore"]
        vsphere_module = importlib.import_module("ocs-ci.ocs_ci.utility.vsphere")
        self.vsphere_utils = vsphere_module.VSPHERE(host=self.host, user=self.username, password=self.password)
        self.lockable_resources_num = env_dict["lockable_resources_num"]

    def get_datastore_free_capacity_percentage(self):
        ds_obj = self.vsphere_utils.find_datastore_by_name(self.datastore, self.dc_name)
        return ds_obj.summary.freeSpace / ds_obj.summary.capacity

    def get_free_memory_percentage(self):
        cluster_obj = self.vsphere_utils.get_cluster(self.cluster_name, self.dc_name)
        return cluster_obj.GetResourceUsage().memUsedMB / cluster_obj.GetResourceUsage().memCapacityMB

    def get_free_cpu_percentage(self):
        cluster_obj = self.vsphere_utils.get_cluster(self.cluster_name, self.dc_name)
        return cluster_obj.GetResourceUsage().cpuUsedMHz / cluster_obj.GetResourceUsage().cpuCapacityMHz

    def get_cluster_details(self, hint_type, vm_list):
        run_time = 0
        prefix = self.get_cluster_name_prefix(self.cluster_name.split("-"))
        storage_usage = 0
        memory_usage = 0
        cpu_usage = 0
        for vm in vm_list:
            if hint_type in vm.name:
                run_time = self.get_run_time(vm)
            storage_usage += self.get_vm_storage_usage(vm)
            memory_usage += self.get_vm_memory_usage(vm)
            cpu_usage += self.get_vm_cpu_usage(vm)
        storage_usage = storage_usage / 1e+12
        return run_time, storage_usage, memory_usage, cpu_usage, prefix

    def get_run_time(self, vm):
        now = datetime.datetime.now()
        naive = vm.config.createDate.replace(tzinfo=None)
        run_time = now - naive
        return int(run_time.total_seconds() / 3600)

    def get_vm_storage_usage(self, vm):
        vm_storage_usage = 0
        for disk in vm.storage.perDatastoreUsage:
            vm_storage_usage += disk.unshared
        return vm_storage_usage

    def get_vm_memory_usage(self, vm):
        return vm.summary.quickStats.hostMemoryUsage / 1024

    def get_vm_cpu_usage(self, vm):
        return vm.summary.quickStats.overallCpuUsage / 1000


class AWSOps(OpsBase):
    """
    """
    def __init__(self):
        super(AWSOps, self).__init__()
        self.aws_module = importlib.import_module("ocs-ci.ocs_ci.utility.aws")

    def set_env_details(self, env_dict):
        """
        """
        self.region_name = env_dict["region_name"]
        self.aws_ops = self.aws_module.AWS(region_name=self.region_name)

    def get_cluster_details(self, ec2_instances):
        cluster_running_time = 0
        num_of_instances = 0
        instance_types = list()

        for instance in ec2_instances:
            num_of_instances += 1
            if instance.state["Name"] == "running":
                launch_time = instance.launch_time
                current_time = datetime.datetime.now(launch_time.tzinfo)
                instance_running_time = current_time - launch_time
                if instance_running_time.total_seconds() > cluster_running_time:
                    cluster_running_time = instance_running_time.total_seconds()
            instance_type = instance.instance_type
            if instance_type not in instance_types:
                instance_types.append(instance_type)
        return int(cluster_running_time/3600), num_of_instances, ', '.join(instance_types)


class AzureOps(OpsBase):
    """
    """
    def __init__(self):
        super(AzureOps, self).__init__()
        path = sys.path[0]
        print(path)
        sys.path.append("/home/elad/python_projects/ocs-ci")
        self.azure_module = importlib.import_module("ocs-ci.ocs_ci.utility.azure_utils")

    def set_env_details(self, env_dict):
        """
        """
        path = sys.path[0]
        print(path)
        sys.path.append("/home/elad/python_projects/ocs-ci")
        
        self.credential = ClientSecretCredential(
            tenant_id=env_dict['tenant_id'],
            client_id=env_dict['client_id'],
            client_secret=env_dict['client_secret']
        )
        rmc = self.azure_module.ResourceManagementClient(self.credential, env_dict["subscription_id"])
        self.subscription_id = env_dict["subscription_id"]
        self.resource_group_list = rmc.resource_groups.list()
        self.azure_utils = self.azure_module.AZURE(
            subscription_id=env_dict["subscription_id"],
            tenant_id=env_dict['tenant_id'],
            client_id=env_dict['client_id'],
            client_secret=env_dict['client_secret'],
            cluster_resource_group=env_dict['cluster_resource_group']
        )


class GCPOps(OpsBase):
    """
    """
    def __init__(self):
        super(GCPOps, self).__init__()
        path = sys.path[0]
        print(path)
        sys.path.append("/home/elad/python_projects/ocs-ci")
        self.gcp_module = importlib.import_module("ocs-ci.ocs_ci.utility.gcp")


    def set_env_details(self, env_dict):
        """
        """
        path = sys.path[0]
        print(path)
        sys.path.append("/home/elad/python_projects/ocs-ci")
        self.gcp_utils = self.gcp_module.GoogleCloud(project_id=GCP_PROJECT_ID)
        set_trace()



class IBMCloudOps(OpsBase):
    """
    """
    def __init__(self):
        super(IBMCloudOps, self).__init__()
        path = sys.path[0]
        print(path)
        sys.path.append("/home/elad/python_projects/ocs-ci")
        self.ibm_cloud_module = importlib.import_module("ocs-ci.ocs_ci.utility.ibmcloud")

    def set_env_details(self, env_dict):
        """
        """
        path = sys.path[0]
        print(path)
        sys.path.append("/home/elad/python_projects/ocs-ci")
        utils = importlib.import_module("ocs-ci.ocs_ci.utility.utils")
        self.run_cmd = utils.run_cmd 
        
        login_cmd = f"/usr/local/bin/ibmcloud login --apikey {env_dict['api_key']} -c {env_dict['account_id']} -r {env_dict['region']}"
        self.run_cmd(login_cmd)
        
        self.ibm_cloud_utils = self.ibm_cloud_module.IBMCloud()


class ReportsBase:
    def get_resource_consumption_report():
        pass


class VsphereReports(ReportsBase):

    def get_resource_consumption_report(self):
        """
        """

        self.vsphere_report = f"<br><b><u><h3>vSphere Consumption Report</h3><u></b>"
        field_names = [
            "vSphere Env",
            "Cluster Name",
            "Deployment Type",
            "Number Of VMs",
            "Run Time",
            "Memory Usage",
            "CPU Usage",
            "Storage Usage",
            "Comments"
        ]
        min_diff = 0.15
        resources_list = list()
        # for vsphere_env_dict in VSPHERE_ENV_DICT_LIST:
        def generate_dc_report(vsphere_env_dict):
            
            vsphere_ops = VsphereOps()
            vsphere_ops.set_env_details(vsphere_env_dict)
            resources = dict()
            resources['vsphere_env'] = vsphere_ops.host
            table = PrettyTable()
            table.field_names = field_names
            free_space_per = vsphere_ops.get_datastore_free_capacity_percentage()
            storage_utilization = (1 - free_space_per) * 100
            if free_space_per < min_diff:
                print(
                    f"There is not enough space available on {resources['vsphere_env']} <i>{vsphere_ops.dc_name}</i>'s datastore <i>{vsphere_ops.datastore}</i>. Used space is {storage_utilization:.1f}%"
                )

            free_memory_per = vsphere_ops.get_free_memory_percentage()
            memory_utilization = free_memory_per * 100
            if free_memory_per < min_diff:
                print(
                    f"There is not enough memory available on {resources['vsphere_env']} <i>{vsphere_ops.dc_name}</i>'s cluster <i>{vsphere_ops.cluster_name}</i>. Used memory is {memory_utilization:.1f}%"
                )

            free_cpu_per = vsphere_ops.get_free_cpu_percentage()
            cpu_utilization = free_cpu_per * 100
            if free_cpu_per < min_diff:
                print(
                    f"There are not enough available CPUs on {resources['vsphere_env']} <i>{vsphere_ops.dc_name}</i>'s cluster <i>{vsphere_ops.cluster_name}</i>. Used CPU is {cpu_utilization:.1f}%"
                )

            resources['storage_utilization'] = f"{storage_utilization:.1f}%"
            resources['memory_utilization'] = f"{memory_utilization:.1f}%"
            resources['cpu_utilization'] = f"{cpu_utilization:.1f}%"

            cluster_obj = vsphere_ops.vsphere_utils.get_cluster(vsphere_ops.cluster_name, vsphere_ops.dc_name)

            parent_rp = cluster_obj.resourcePool
            parent_rp_vms = [vm for vm in parent_rp.vm if not any(x in vm.name for x in IGNORE_LIST)]

            rps = cluster_obj.resourcePool.resourcePool

            run_times = list()
            def add_cluster_to_table(cluster_name, cluster_name_refined, vm_list, hint):
                if 'jnk' not in cluster_name:
                    run_time, storage_usage, memory_usage, cpu_usage, _ = vsphere_ops.get_cluster_details(hint, vm_list)
                    comments = ""

                    if run_time > HIGH_RUN_TIME:
                        comments += f"This cluster is running for {int(run_time / 24)} days."
                    if comments:
                        comments += f"\n"
                    if storage_usage > HIGH_STORAGE:
                        comments += f"This cluster is consuming a considerable amount of space."
                    if memory_usage > HIGH_MEMORY:
                        comments += f"\nThis cluster is consuming a considerable amount of memory."

                    deployment_type = "IPI" if hint == IPI_HINT else "UPI"
                    
                    run_times.append(run_time) 
                    table.add_row(
                        [vsphere_ops.host, cluster_name_refined, deployment_type, len(vm_list), f"{run_time} H", f"{memory_usage:.1f} GB", f"{cpu_usage:.1f} GHz", f"{storage_usage:.2f} TB", comments]
                    )


            for rp in rps:
                try:
                    cluster_name = rp.name
                except Exception as ex:
                    print(ex)

                cluster_name_refined = cluster_name
                vm_list = rp.vm
                add_cluster_to_table(cluster_name, cluster_name_refined, vm_list, UPI_HINT)

            vm_dict = defaultdict(list)
            for vm in parent_rp_vms:
                vm_dict[vm.name.split('-')[0]].append(vm)
            parent_rp_lists = vm_dict.values()

            for vm_list in parent_rp_lists:
                cluster_name = vm_list[0].name
                cluster_name.split("-")
                cluster_name_refined = '-'.join(cluster_name.split("-")[:2])
                add_cluster_to_table(cluster_name, cluster_name_refined, vm_list, IPI_HINT)

            resources['rps_num'] = len(rps) + len(parent_rp_lists)
            resources['lockable_resources_num'] = vsphere_ops.lockable_resources_num

            refined_table = vsphere_ops.set_table(table, run_times)


            resources['table'] = refined_table
            resources_list.append(resources)

            if resources['rps_num'] > 0:
                self.vsphere_report += (
                    f"<u>In {resources['vsphere_env']}, <i>{vsphere_ops.dc_name}</i>'s utilization details are:</u>"
                    f"<br><b>Lockable Resources:</b> <b>{resources['rps_num']} out of {resources['lockable_resources_num']}</b> available resources are currently in use"
                    f"<br><b>Storage:</b> Datastore <i>{vsphere_ops.datastore}</i> utilization is at <b>{resources['storage_utilization']}</b>"
                    f"<br><b>Memory:</b> Overall Memory utilization is at <b>{resources['memory_utilization']}</b></br>"
                    f"<br><b>CPU:</b> Overall CPU utilization is at <b>{resources['cpu_utilization']}</b></br>"
                    f"<br><br>"
                    f"The following <b>{resources['rps_num']}</b> ODF/OCP/ACM clusters are currently running on <i>{vsphere_ops.dc_name}</i>"
                    f"<br><br>{resources['table']}<br><br>"
                )
        # indices = range(len(VSPHERE_ENV_DICT_LIST))
        thread_list = list()
        for vsphere_env_dict in VSPHERE_ENV_DICT_LIST:
            thread_list.append(threading.Thread(target=generate_dc_report, args=(vsphere_env_dict,)))
        for thread in thread_list:
            thread.start()
        for thread in thread_list:
            thread.join()
        report = self.vsphere_report
        return report


class AWSReports(ReportsBase):

    def get_resource_consumption_report(self):
        """
        """
        aws_ops = AWSOps()
        aws_ops.set_env_details(env_dict=AWS_ENV_DICT)

        table = PrettyTable()
        table.field_names = [
            "Region",
            "Cluster Name",
            "Number Of EC2 Instances",
            "EC2 Instance Types",
            "Run Time",
            "Comments"
        ]
        run_times = list()
        def add_cluster_to_table(cluster_name, cluster_running_time, num_of_instances, instance_types):
            if 'vault' in cluster_name:
                return
            cluster_name_parts = cluster_name.split("-")
            index = 1 if any(x in cluster_name for x in ["dnd", "lr"]) else 0
            prefix = aws_ops.get_cluster_name_prefix(cluster_name_parts, index)


            comments = ""
            if cluster_running_time > 72:
                comments += f"This cluster is running for {int(cluster_running_time / 24)} days."
                # if recipient and recipient not in TO_LIST:
                #     TO_LIST.append(recipient)
            run_times.append(cluster_running_time)
            table.add_row([aws_ops.region_name, cluster_name, num_of_instances, instance_types, f"{cluster_running_time} H", comments])

        number_of_clusters = 0
        vmless_clusters = list()

        cloudformation_vpc_names = list()
        vpcs = aws_ops.aws_ops.ec2_client.describe_vpcs()["Vpcs"]
        vpc_ids = [vpc["VpcId"] for vpc in vpcs]
        vpc_objs = [aws_ops.aws_ops.ec2_resource.Vpc(vpc_id) for vpc_id in vpc_ids]
        for vpc_obj in vpc_objs:
            vpc_tags = vpc_obj.tags
            if vpc_tags:
                cloudformation_vpc_name = [
                    tag["Value"] for tag in vpc_tags if tag["Key"] == AWS_CLOUDFORMATION_TAG
                ]
                if cloudformation_vpc_name:
                    cloudformation_vpc_names.append(cloudformation_vpc_name[0])
                    continue
                vpc_name = [tag["Value"] for tag in vpc_tags if tag["Key"] == "Name"][0]
                cluster_name = vpc_name.replace("-vpc", "")
                ec2_instances = vpc_obj.instances.all()

                cluster_running_time, num_of_instances, instance_types = aws_ops.get_cluster_details(ec2_instances)
                if num_of_instances > 0:
                    add_cluster_to_table(cluster_name, cluster_running_time, num_of_instances, instance_types)
                    number_of_clusters += 1
                else:
                    vmless_clusters.append(cluster_name)

        # Get all cloudformation based clusters to delete
        for vpc_name in cloudformation_vpc_names:
            instance_dicts = aws_ops.aws_ops.get_instances_by_name_pattern(
                f"{vpc_name.replace('-vpc', '')}*"
            )
            ec2_instances = [
                aws_ops.aws_ops.get_ec2_instance(instance_dict["id"])
                for instance_dict in instance_dicts
            ]
            if not ec2_instances:
                continue
            cluster_io_tag = None
            for instance in ec2_instances:
                cluster_io_tag = [
                    tag["Key"]
                    for tag in instance.tags
                    if "kubernetes.io/cluster" in tag["Key"]
                ]
                if cluster_io_tag:
                    break
            if not cluster_io_tag:
                continue
            cluster_name = cluster_io_tag[0].replace("kubernetes.io/cluster/", "")

            cluster_running_time, num_of_instances, instance_types = aws_ops.get_cluster_details(ec2_instances)
            add_cluster_to_table(cluster_name, cluster_running_time, num_of_instances, instance_types)
            number_of_clusters += 1

        refined_table = aws_ops.set_table(table, run_times)
        report = "<br><b><u><h3>AWS Consumption Report</h3></u></b>"
        if number_of_clusters > 0:
            report += (
                f"<u>The following <b>{number_of_clusters}</b> ODF/OCP/ACM clusters are currently running</u>"
                f"<br><br>{refined_table}<br><br>"
            )
            if len(vmless_clusters) > 0:
                vmless_clusters = '<br>'.join(vmless_clusters)
                report += (
                    f"<u>In addition, the following leftover VM-less VPCs and their associated resources still exist:</u><br>{vmless_clusters}<br>"
                )
        return report


class AzureReports(ReportsBase):

    def get_resource_consumption_report(self):
        """
        """
        table = PrettyTable()
        table.field_names = [
            "Cluster Name",
            "Number Of Instances",
            "Instances Types",
            "Creation Time (UTC)",
            "Azure Account",
        ]
        number_of_clusters = 0
        azure_dict = AZURE_DICT
        azure_ops = AzureOps()
        azure_ops.set_env_details(azure_dict)
        group_list = [rg for rg in azure_ops.resource_group_list if rg.name.endswith("-rg")]
        number_of_clusters += len(group_list)
        vm_client = azure_ops.azure_module.ComputeManagementClient(azure_ops.credential, azure_ops.subscription_id)
        
        for rg in group_list:
            azure_ops.azure_utils._cluster_resource_group = rg.name
            vm_list = vm_client.virtual_machines.list(rg.name)
            num_of_vms = 0
            vm_types = list()
            launch_time = 0
            for vm in vm_list:
                num_of_vms += 1
                vm = vm_client.virtual_machines.get(rg.name, vm.name, expand="instanceView")
                if IPI_HINT in vm.name:
                    launch_time = vm.instance_view.statuses[0].as_dict()['time'].split('T')
                    launch_time[1] = launch_time[1].split('.')[0]
                    launch_time = " ".join(launch_time)

                vm_type = vm.hardware_profile.vm_size
                if vm_type not in vm_types:
                    vm_types.append(vm_type)
            table.add_row([rg.name.replace("-rg", ""), num_of_vms, ', '.join(vm_types), launch_time, azure_dict['account']])
        refined_table = azure_ops.set_table(table)
        report = "<br><b><u><h3>Azure Consumption Report</h3></u></b>"
        if number_of_clusters > 0:
            report += (
                f"<u>The following <b>{number_of_clusters}</b> ODF/OCP/ACM clusters are currently running</u>"
                f"<br><br>{refined_table}<br><br>"
            )
        return report


class IBMCloudReports(ReportsBase):

    def get_resource_consumption_report(self):
        """
        """

        table = PrettyTable()
        table.field_names = [
            "Region",
            "Cluster Name",
            "Number Of VM Instances",
            "Run Time",
            "Associated Resource Types"
        ]

        table_rows = list()
        number_of_clusters = 0

        for cloud_dict in IBM_CLOUD_DICTS:

            ibm_cloud_ops = IBMCloudOps()
            ibm_cloud_ops.set_env_details(env_dict=cloud_dict)


            run_times = list()
            out = ibm_cloud_ops.run_cmd("/usr/local/bin/ibmcloud resources --output=json")
            out = json.loads(out)
            
            resources = out['items']
            resources = [resource for resource in resources if 'doc' in resource]
            resources = [resource for resource in resources if 'resource_group_id' in resource['doc']]


            resource_groups_raw = ibm_cloud_ops.run_cmd("/usr/local/bin/ibmcloud resource groups --output=json")
            resource_groups = json.loads(resource_groups_raw)


            out = ibm_cloud_ops.run_cmd('/usr/local/bin/ibmcloud resource search "type:instance" --output=json')
            out = json.loads(out)
            instances = out['items']

            
            
            resource_groups = [rg for rg in resource_groups if rg['name'] not in ['odf-qe', 'Default']]
            number_of_clusters += len(resource_groups)

            for rg in resource_groups:
                rg_instances = [instance for instance in instances if instance['doc']['resource_group']['id'] == rg['id']]
                out = ibm_cloud_ops.run_cmd(f'/usr/local/bin/ibmcloud resource search doc.resource_group.id:{rg["id"]} --output=json')
                out = json.loads(out)
                resources = out['items']
                rg_resource_types = [resource['type'] for resource in resources]
                rg_resource_types = list(set(rg_resource_types))

                region = None
                created_at = rg['created_at']
                creation_time = datetime.datetime.strptime(created_at, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=datetime.timezone.utc)
                current_time = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
                time_difference = current_time - creation_time
                cluster_running_time = int(time_difference.total_seconds() / 3600)
                
                if len(rg_instances) > 0:
                    region = rg_instances[0]['region']

                run_times.append(cluster_running_time)
                table_rows.append([region, rg['name'], len(rg_instances), f"{cluster_running_time} H", ', '.join(rg_resource_types)])
            
            

        table_rows = sorted(table_rows, key=lambda x: x[2], reverse=True)

        
        for row in table_rows:
            table.add_row(row)


        refined_table = ibm_cloud_ops.set_table(table, run_times)
        report = "<br><b><u><h3>IBM Cloud Consumption Report</h3></u></b>"
        if number_of_clusters > 0:
            report += (
                f"<u>The following <b>{number_of_clusters}</b> ODF/OCP/ACM clusters are currently running</u>"
                f"<br><br>{refined_table}<br><br>"
            )
        return report


def get_resource_consumption_reports():
    """
    """
    final_report = ""
    for platform in [AzureReports, AWSReports, IBMCloudReports, VsphereReports]:
    # for platform in [AzureReports, AWSReports, IBMCloudReports]:

        platform_obj = platform()
        report = platform_obj.get_resource_consumption_report()
        if report:
            final_report += platform_obj.get_resource_consumption_report()

    return final_report


def get_dc_utilization_data():


    g_sheet_module = importlib.import_module(f"ocs-ci.ocs_ci.utility.spreadsheet.spreadsheet_api")

    indices = range(len(VSPHERE_ENV_DICT_LIST))

    def set_data(vsphere_env_dict, index):
        vsphere_ops = VsphereOps()
        vsphere_ops.set_env_details(vsphere_env_dict)
        g_sheet = g_sheet_module.GoogleSpreadSheetAPI(sheet_name=SHEET_NAME, sheet_index=index)
        print(g_sheet.sheet)

        while True:

            now = datetime.datetime.now()
            date = now.strftime("%m/%d/%y")
            current_time = now.strftime("%H:%M")

            cluster_obj = vsphere_ops.vsphere_utils.get_cluster(vsphere_ops.cluster_name, vsphere_ops.dc_name)
            parent_rp = cluster_obj.resourcePool
            parent_rp_vms = [vm for vm in parent_rp.vm if not any(x in vm.name for x in IGNORE_LIST)]
            rps = cluster_obj.resourcePool.resourcePool
            vm_dict = defaultdict(list)
            for vm in parent_rp_vms:
                vm_dict[vm.name.split('-')[0]].append(vm)
            parent_rp_lists = vm_dict.values()

            num_of_clusters = len(rps) + len(parent_rp_lists)

            free_space_per = (vsphere_ops.get_datastore_free_capacity_percentage())
            storage_utilization = 1 - free_space_per

            free_memory_per = vsphere_ops.get_free_memory_percentage()
            memory_utilization = free_memory_per

            free_cpu_per = vsphere_ops.get_free_cpu_percentage()
            cpu_utilization = free_cpu_per

            values = [date, current_time, num_of_clusters, storage_utilization, memory_utilization, cpu_utilization]

            print(f"Time is: {current_time}. Updating sheet: {g_sheet.sheet}")
            g_sheet.insert_row(values, 2)

    thread_list = list()
    for vsphere_env_dict, index in zip(VSPHERE_ENV_DICT_LIST, indices):
        thread_list.append(threading.Thread(target=set_data, args=(vsphere_env_dict, index,)))
    for thread in thread_list:
        thread.start()
    for thread in thread_list:
        thread.join()


def utilization_report_to_email():
    """
    """
    start_time = datetime.datetime.utcnow()

    sender = 'ebenahar@redhat.com'
    # TO_LIST.append('ocs-qe@redhat.com')
    subject = f'ODF QE On-Prem and Cloud Resource Consumption Report'

    text = (
        f"Hello,<br><br>Below is a report about ODF QE's On-Prem and Cloud resource consumption."
        f"<br><br><b>Please destroy any cluster that is not in use.</b><br><br>"
    )

    text = text + get_resource_consumption_reports()

    msg = MIMEMultipart('alternative')
    # to = ", ".join(TO_LIST)
    to = "ocs-qe@redhat.com"
    #to = "ebenahar@redhat.com"
    msg['Subject'] = subject

    # msg_p1 = MIMEText(text, 'plain', 'UTF-8')
    msg_p2 = MIMEText(text, 'html', 'UTF-8')

    # msg.attach(msg_p1)
    msg.attach(msg_p2)

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.ehlo()
    server.starttls()
    server.login(EMAIL_SENDER_USERNAME, EMAIL_SENDER_PASSWORD)
    server.sendmail(sender, to, msg.as_string())
    server.close()

    now = datetime.datetime.utcnow()
    execution_time = now - start_time
    print(f"Execution time: {round((execution_time.seconds / 60), 1)} minutes")


def resource_usage_reporter():
    parser = argparse.ArgumentParser(
        description="Resource Usage Reporter",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--sheet",
        required=False,
        help="The mode of report to append utilization values in Google Spreadsheet",
    )
    parser.add_argument(
        "--email",
        action="store",
        required=False,
        help="The mode of report to send an email",
    )
    parser.add_argument(
        "--vm-dc",
        action="store",
        required=False,
        help="The vSphere Datacenter to get the info for",
    )

    return parser.parse_args()


if __name__ == '__main__':
    remove_ocsci_dir()
    clone_ocsci()
    args = resource_usage_reporter()
    if args.sheet:
        get_dc_utilization_data()
    if args.email:
        utilization_report_to_email()
    remove_ocsci_dir()
