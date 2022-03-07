from __future__ import print_function
import os
import re
import ssl
import sys
import requests
import atexit
import smtplib
import tempfile
import datetime
from subprocess import check_output
import smtplib
import datetime
import importlib
from subprocess import check_output
from collections import defaultdict

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from prettytable import PrettyTable
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage
from email.headerregistry import Address
from email.mime.text import MIMEText
from termcolor import colored
from prettytable import PrettyTable
from pyVim import connect
from pyVmomi import vim
from pyVim.connect import Disconnect, SmartStubAdapter, VimSessionOrientedStub

BASE_VSPHERE_ENV_DICT = {
    "host": "",
    "username": "",
    "password": "",
    "port": 443,
    "cluster_name": "",
    "dc_name": "",
    "datastore": "",
    "lockable_resources_num": None
}

DIVIDER_STR = "<br>" + "-" * 75 + "<br>"

# Use BASE_VSPHERE_ENV_DICT and extend it with the relevant details
VSPHERE_ENV_DICT_LIST = list()

IPI_HINT = 'master-'
UPI_HINT = 'lb-'

# AWS details
AWS_CLOUDFORMATION_TAG = None
ENV_DICT = {"region_name": ""}

EMAIL_SENDER_USERNAME = ""
EMAIL_SENDER_PASSWORD = ""
SMTP_DETAILS = None
RECIPIENTS_LIST = ""

MAIL_SUFFIX = None
IGNORE_LIST = list()

sslContext = ssl._create_unverified_context()
HEADER = '\033[95m'


class OpsBase:
    """
    """
    def __init__(self):
        self.remove_ocsci_dir()
        cmd = 'git clone https://github.com/red-hat-storage/ocs-ci.git'
        check_output(cmd, shell=True).decode()

    def remove_ocsci_dir(self):
        cmd = 'rm -rf ocs-ci'
        check_output(cmd, shell=True).decode()

    def get_resource_consumption_report(self):
        pass

    def __del__(self):
        self.remove_ocsci_dir()

    def get_cluster_name_prefix(self, parts, index=0):
        prefix = parts[index]
        return re.sub(r'[0-9]', '', prefix)

    def get_cluster_details(self):
        pass

    def set_table(self, table):
        table.sortby = "Run Time (in Hours)"
        table.reversesort = True
        return table.get_html_string(
            attributes={
                'border': 1,
                'style': 'border-width: 1px; border-collapse: collapse; text-align: center; padding: 2px;'
            }
        )


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
        vsphere_module = importlib.import_module(f"ocs-ci.ocs_ci.utility.vsphere")
        self.vsphere_ops = vsphere_module.VSPHERE(host=self.host, user=self.username, password=self.password)
        self.lockable_resources_num = env_dict["lockable_resources_num"]

    def get_datastore_free_capacity_percentage(self, datastore_name, datacenter_name):
        ds_obj = self.vsphere_ops.find_datastore_by_name(datastore_name, datacenter_name)
        return ds_obj.summary.freeSpace / ds_obj.summary.capacity

    def get_cluster_details(self, cluster_name, hint_type, vm_list):
        run_time = 0
        prefix = self.get_cluster_name_prefix(cluster_name.split("-"))
        storage_usage = 0
        for vm in vm_list:
            if hint_type in vm.name:
                run_time = self.get_run_time(vm)
            storage_usage += self.get_vm_storage_usage(vm)
        storage_usage = storage_usage / 1e+12
        return run_time, storage_usage, prefix

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

    def get_resource_consumption_report(self):
        """
        """
        field_names = [
            "vSphere Env",
            "Cluster Name",
            "Number Of VMs",
            "Run Time (in Hours)",
            "Usage On Datastore",
            "Comments"
        ]

        min_diff = 0.15
        resources_list = list()
        to_list = list()
        for vsphere_env_dict in VSPHERE_ENV_DICT_LIST:
            self.set_env_details(vsphere_env_dict)
            resources = dict()
            resources['vsphere_env'] = self.host
            table = PrettyTable()
            table.field_names = field_names

            free_space_per = self.get_datastore_free_capacity_percentage(datastore_name=self.datastore, datacenter_name=self.dc_name)
            utilization = (1 - free_space_per) * 100
            if free_space_per < min_diff:
                print(
                    f"There is not enough space on {resources['vsphere_env']} <i>{self.dc_name}</i>'s datastore <i>{self.datastore}</i>. Used space is {utilization:.1f}%"
                )
            resources['utilization'] = f"{utilization:.1f}%"

            cluster_obj = self.vsphere_ops.get_cluster(self.cluster_name, self.dc_name)

            parent_rp = cluster_obj.resourcePool
            parent_rp_vms = [vm for vm in parent_rp.vm if not any(x in vm.name for x in IGNORE_LIST)]

            rps = cluster_obj.resourcePool.resourcePool

            def add_cluster_to_table(cluster_name, cluster_name_refined, vm_list, hint):
                if 'jnk' not in cluster_name:
                    run_time, storage_usage, prefix = self.get_cluster_details(cluster_name, hint, vm_list)
                    recipient = None
                    comments = ""
                    if prefix is not None:
                        recipient = f"{prefix}{MAIL_SUFFIX}"

                    if run_time > 72:
                        comments += f"{recipient} - This cluster is running for {int(run_time / 24)} days."
                        if recipient not in to_list:
                            to_list.append(recipient)
                    if comments:
                        comments += f"\n"
                    if storage_usage > 3:
                        if recipient not in to_list:
                            to_list.append(recipient)
                        if not comments:
                            comments += f"{recipient} - "
                        comments += f"This cluster is consuming a considerable amount of space"
                    table.add_row(
                        [self.host, cluster_name_refined, len(vm_list), f"{run_time}", f"{storage_usage:.2f} TB", comments]
                    )

            for rp in rps:
                cluster_name = rp.name
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
            resources['lockable_resources_num'] = self.lockable_resources_num

            refined_table = self.set_table(table)
            resources['table'] = refined_table
            resources_list.append(resources)

        report = f"<br><b>vSphere Consumption Report</b><br>{DIVIDER_STR}<br>"
        for resources in resources_list:
            if resources['rps_num'] > 0:
                report += (
                    f"<u>In {resources['vsphere_env']}, <i>{self.dc_name}</i>'s utilization details are:</u>"
                    f"<br>Datastore <i>{self.datastore}</i> utilization: <b>{resources['utilization']}</b>"
                    f"<br>Lockable Resources Utilization: <b>{resources['rps_num']} out of {resources['lockable_resources_num']}</b> available resources are currently in use"
                    f"<br><br>"
                    f"The following <b>{resources['rps_num']}</b> ODF/OCP/ACM clusters are currently running on <i>{self.dc_name}</i>"
                    f"<br><br>{resources['table']}<br><br>"
                )
        return report


class AWSOps(OpsBase):
    """
    """
    def __init__(self):
        super(AWSOps, self).__init__()
        self.set_env_details(env_dict=ENV_DICT)

    def set_env_details(self, env_dict):
        """
        """
        self.region_name = env_dict["region_name"]
        aws_module = importlib.import_module(f"ocs-ci.ocs_ci.utility.aws")
        self.aws_ops = aws_module.AWS(region_name=self.region_name)

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

    def get_resource_consumption_report(self):
        """
        """
        table = PrettyTable()
        table.field_names = [
            "Region",
            "Cluster Name",
            "Number Of EC2 Instances",
            "EC2 Instance Types",
            "Run Time (in Hours)",
            "Comments"
        ]

        to_list = list()

        def add_cluster_to_table(cluster_name, cluster_running_time, num_of_instances, instance_types):
            if 'vault' in cluster_name:
                return
            cluster_name_parts = cluster_name.split("-")
            index = 1 if any(x in cluster_name for x in ["dnd", "lr"]) else 0
            prefix = self.get_cluster_name_prefix(cluster_name_parts, index)

            recipient = None

            if prefix is not None and 'jnk' not in prefix:
                recipient = f"{prefix}{MAIL_SUFFIX}"

            comments = ""
            if cluster_running_time > 72:
                comments += f"{recipient} - This cluster is running for {int(cluster_running_time / 24)} days."
                if recipient and recipient not in to_list:
                    to_list.append(recipient)
            table.add_row([self.region_name, cluster_name, num_of_instances, instance_types, f"{cluster_running_time}", comments])

        number_of_clusters = 0

        cloudformation_vpc_names = list()
        vpcs = self.aws_ops.ec2_client.describe_vpcs()["Vpcs"]
        vpc_ids = [vpc["VpcId"] for vpc in vpcs]
        vpc_objs = [self.aws_ops.ec2_resource.Vpc(vpc_id) for vpc_id in vpc_ids]
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

                cluster_running_time, num_of_instances, instance_types = self.get_cluster_details(ec2_instances)
                add_cluster_to_table(cluster_name, cluster_running_time, num_of_instances, instance_types)
                number_of_clusters += 1

        # Get all cloudformation based clusters to delete
        for vpc_name in cloudformation_vpc_names:
            instance_dicts = self.aws_ops.get_instances_by_name_pattern(
                f"{vpc_name.replace('-vpc', '')}*"
            )
            ec2_instances = [
                aws.get_ec2_instance(instance_dict["id"])
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

            cluster_running_time, num_of_instances, instance_types = self.get_cluster_details(ec2_instances)
            add_cluster_to_table(cluster_name, cluster_running_time, num_of_instances, instance_types)
            number_of_clusters += 1

        refined_table = self.set_table(table)
        report = "<br><b>AWS Consumption Report</b><br>"
        if number_of_clusters > 0:
            report += (
                f"{DIVIDER_STR}<br>"
                f"<u>The following <b>{number_of_clusters}</b> ODF/OCP/ACM clusters exist in AWS (region {self.region_name})</u>"
                f"<br><br>{refined_table}<br><br>"
            )
        return report


class AzureOps(OpsBase):
    """
    """
    def __init__(self):
        super(AzureOps, self).__init__()


def get_resource_consumption_reports():
    """
    """
    final_report = ""
    for platform in [VsphereOps, AWSOps]:
        platform_obj = platform()
        final_report += platform_obj.get_resource_consumption_report()

    return final_report


def send_email():
    """

    """
    sender = EMAIL_SENDER_USERNAME
    to = RECIPIENTS_LIST
    subject = f'ODF QE On-Prem and Cloud Resource Consumption Report'

    text = (
        f"Hello,<br><br>Below is a report about ODF QE's On-Prem and Cloud resource consumption."
        f"<br><br><b>Please destroy any cluster that is not in use.</b><br><br>"
    )

    text = text + get_resource_consumption_reports()

    user = EMAIL_SENDER_USERNAME
    pwd = EMAIL_SENDER_PASSWORD

    msg = MIMEMultipart('alternative')
    msg['From'] = sender
    msg['To'] = to
    msg['Subject'] = subject

    # msg_p1 = MIMEText(text, 'plain', 'UTF-8')
    msg_p2 = MIMEText(text, 'html', 'UTF-8')

    # msg.attach(msg_p1)
    msg.attach(msg_p2)

    server = SMTP_DETAILS
    server.ehlo()
    server.starttls()
    server.login(user, pwd)
    server.sendmail(msg['From'], to, msg.as_string())
    server.close()


if __name__ == "__main__":
    send_email()
