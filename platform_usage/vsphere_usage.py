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


class VsphereOps(OpsBase):
    """
    """
    def __init__(self):
        super(VsphereOps, self).__init__()

    def set_vsphere_env_details(self, vsphere_env_dict):
        """

        """
        self.host = vsphere_env_dict["host"]
        self.username = vsphere_env_dict["username"]
        self.password = vsphere_env_dict["password"]
        self.port = vsphere_env_dict["port"]
        self.dc_name = vsphere_env_dict["dc_name"]
        self.cluster_name = vsphere_env_dict["cluster_name"]
        self.datastore = vsphere_env_dict["datastore"]
        vsphere_module = importlib.import_module(f"ocs-ci.ocs_ci.utility.vsphere")
        self.vsphere_ops = vsphere_module.VSPHERE(host=self.host, user=self.username, password=self.password)
        self.lockable_resources_num = vsphere_env_dict["lockable_resources_num"]

    def get_datastore_free_capacity_percentage(self, datastore_name, datacenter_name):
        ds_obj = self.vsphere_ops.find_datastore_by_name(datastore_name, datacenter_name)
        return ds_obj.summary.freeSpace / ds_obj.summary.capacity

    def get_resource_consumption_report(self):
        """
        """
        def get_cluster_name_prefix(parts):
            prefix = parts[0]
            return re.sub(r'[0-9]', '', prefix)

        def get_run_time(now, vm):
            naive = vm.config.createDate.replace(tzinfo=None)
            run_time = now - naive
            return int(run_time.total_seconds() / 3600)

        def get_vm_storage_usage(vm):
            vm_storage_usage = 0
            for disk in vm.storage.perDatastoreUsage:
                vm_storage_usage += disk.unshared
            return vm_storage_usage

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
            self.set_vsphere_env_details(vsphere_env_dict)
            resources = dict()
            resources['vsphere_env'] = self.host
            table = PrettyTable()
            table.field_names = field_names

            free_space_per = self.get_datastore_free_capacity_percentage(datastore_name=self.datastore, datacenter_name=self.dc_name)
            utilization = (1 - free_space_per) * 100
            if free_space_per < min_diff:
                print(
                    f"There is not enough space on {resources['vsphere_env']} <i>{self.dc}</i>'s datastore <i>{self.datastore}</i>. Used space is {utilization:.1f}%"
                )
            resources['utilization'] = f"{utilization:.1f}%"

            cluster_obj = self.vsphere_ops.get_cluster(self.cluster_name, self.dc_name)

            parent_rp = cluster_obj.resourcePool
            parent_rp_vms = [vm for vm in parent_rp.vm if not any(x in vm.name for x in IGNORE_LIST)]

            rps = cluster_obj.resourcePool.resourcePool

            now = datetime.datetime.now()
            for rp in rps:
                if 'jnk' not in rp.name:
                    run_time = None
                    recipient = None
                    add_to_list = False
                    cluster_name_parts = rp.name.split("-")
                    prefix = get_cluster_name_prefix(cluster_name_parts)
                    storage_usage = 0
                    for vm in rp.vm:
                        if 'lb-' in vm.name:
                            run_time = get_run_time(now, vm)
                        storage_usage += get_vm_storage_usage(vm)
                    storage_usage = storage_usage / 1e+12
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
                    if add_to_list:
                        to_list.append(recipient)
                    table.add_row(
                        [self.host, rp.name, len(rp.vm), f"{run_time}", f"{storage_usage:.2f} TB", comments])

            vm_dict = defaultdict(list)
            for vm in parent_rp_vms:
                vm_dict[vm.name.split('-')[0]].append(vm)
            parent_rp_lists = vm_dict.values()

            for vm_list in parent_rp_lists:
                if 'jnk' not in vm_list[0].name:
                    recipient = None
                    add_to_list = False
                    cluster_name_parts = vm_list[0].name.split("-")
                    prefix = get_cluster_name_prefix(cluster_name_parts)
                    storage_usage = 0
                    run_time = get_run_time(now, vm_list[0])
                    for vm in vm_list:
                        storage_usage += get_vm_storage_usage(vm)
                    storage_usage = storage_usage / 1e+12
                    comments = ""
                    if prefix is not None:
                        recipient = f"{prefix}{MAIL_SUFFIX}"

                    if run_time > 72:
                        comments += f"{recipient} - This cluster is running for {int(run_time / 24)} days."
                        if recipient not in to_list:
                            to_list.append(recipient)
                    if comments:
                        comments += f"\n"
                    if storage_usage > 2:
                        if recipient not in to_list:
                            to_list.append(recipient)
                        if not comments:
                            comments += f"{recipient} - "
                        comments += f"This cluster is consuming a considerable amount of space"
                    if add_to_list:
                        to_list.append(recipient)
                    table.add_row([self.host, '-'.join(cluster_name_parts[:2]), len(vm_list), f"{run_time}",
                                   f"{storage_usage:.2f} TB", comments])

            resources['rps_num'] = len(rps) + len(parent_rp_lists)
            resources['lockable_resources_num'] = self.lockable_resources_num

            table.sortby = "Run Time (in Hours)"
            table.reversesort = True
            table = table.get_html_string(
                attributes={
                    'border': 1,
                    'style': 'border-width: 1px; border-collapse: collapse; text-align: center; padding: 2px;'
                }
            )
            resources['table'] = table
            resources_list.append(resources)

        report = ""
        for resources in resources_list:
            if resources['rps_num'] > 0:
                report += (
                    f"{DIVIDER_STR}"
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


class AzureOps(OpsBase):
    """
    """
    def __init__(self):
        super(AzureOps, self).__init__()


def get_resource_consumption_reports():
    """

    """
    vsphere_obj = VsphereOps()
    vsphere_report = vsphere_obj.get_resource_consumption_report()

    # aws_obj = AWSOps()
    # aws_report = aws_obj.get_resource_consumption_report()
    #
    # azure_obj = AzureOps()
    # azure_report = azure_obj.get_resource_consumption_report()

    # final_report = vsphere_report + aws_report + azure_report
    final_report = vsphere_report

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
