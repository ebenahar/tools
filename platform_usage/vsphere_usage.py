import smtplib
import datetime
import importlib
from subprocess import check_output

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from prettytable import PrettyTable


email_credentials = {'username': 'FILL_IN', 'password': 'FILL_IN'}
email_recipients = {'from': 'FILL_IN', 'to': 'FILL_IN'}


host = 'FILL_IN'
username = 'FILL_IN'
password = 'FILL_IN'
port = 'FILL_IN'
cluster = 'FILL_IN'
dc = 'FILL_IN'
datastore = 'FILL_IN'


class VsphereOps:
    """

    """
    def __init__(self):
        cmd = 'git clone https://github.com/red-hat-storage/ocs-ci.git'
        check_output(cmd, shell=True).decode()
        vsphere_mod = importlib.import_module(f"ocs-ci.ocs_ci.utility.vsphere")
        self.vsphere = vsphere_mod.VSPHERE(host=host, user=username, password=password)

    def remove_ocsci_dir(self):
        cmd = 'rm -rf ocs-ci'
        check_output(cmd, shell=True).decode()

    def get_datastore_free_capacity_percentage(self, datastore_name, datacenter_name):
        ds_obj = self.vsphere.find_datastore_by_name(datastore_name, datacenter_name)
        return ds_obj.summary.freeSpace / ds_obj.summary.capacity

    def mailer(self, sender, to, subject, text, user, pwd):
        msg = MIMEMultipart('alternative')
        msg['From'] = sender
        msg['To'] = to
        msg['Subject'] = subject

        msg_p1 = MIMEText(text, 'html', 'UTF-8')
        msg.attach(msg_p1)

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.login(user, pwd)
        server.sendmail(msg['From'], to, msg.as_string())
        server.close()

    def usage(self, dc_name, cluster_name):

        cluster_obj = self.vsphere.get_cluster(cluster_name, dc_name)
        rps = cluster_obj.resourcePool.resourcePool

        table = PrettyTable()
        table.field_names = [
            "Cluster Name",
            "Number Of VMs",
            "Run Time (in Hours)",
            "Usage On Datastore",
            "Comments"
        ]

        min_diff = 0.15
        free_space_per = self.get_datastore_free_capacity_percentage(datastore_name=datastore, datacenter_name=dc)
        if free_space_per < min_diff:
            to_list = list()
            now = datetime.datetime.now()
            for rp in rps:
                run_time = None
                prefix = None
                if 'jnk' not in rp.name:
                    cluster_name_parts = rp.name.split("-")
                    prefix = cluster_name_parts[0]
                    prefix.split(r'(?<=\D),\s*|\s*,(?=\D)')
                    to_list.append(prefix)
                storage_usage = 0
                for vm in rp.vm:
                    if 'lb-' in vm.name:
                        naive = vm.config.createDate.replace(tzinfo=None)
                        run_time = now - naive
                        run_time = int(run_time.total_seconds() / 3600)
                    for disk in vm.storage.perDatastoreUsage:
                        storage_usage += disk.unshared
                storage_usage = storage_usage / 1e+12
                comments = ""
                if prefix is not None:
                    prefix = f"{prefix}@redhat.com - "
                if run_time > 72:
                    comments += f"{prefix}This cluster is running for more than 3 days."
                if comments:
                    comments += f"\n"
                if storage_usage > 3:
                    if not comments:
                        comments += f"{prefix}"
                    comments += f"This cluster is consuming a considerable amount of space"
                table.add_row([rp.name, len(rp.vm), run_time, f"{storage_usage:.2f} TB", comments])
            utilization = (1 - free_space_per) * 100
            sender = email_recipients['from']
            to = email_recipients['to']
            subject = f'CRITICAL - vSphere {dc} {datastore} utilization is at {utilization:.1f}%'
            table.sortby = "Run Time (in Hours)"
            table.reversesort = True

            table = table.get_html_string(
                attributes={
                    'border': 1,
                    'style': 'border-width: 1px; border-collapse: collapse; text-align: center; padding: 2px;'
                }
            )
            text = (
                f"Hello,<br><br>This is an automatic notification sent because the utilization of "
                f"{dc}'s datastore {datastore} is critically high - {utilization:.1f}%.<br><br><b>"
                f"Please destroy any cluster that is not in use.</b>"
                f"<br><br>The following {len(rps)} OCS clusters are currently running on {dc}:<br><br>{table}"
            )
            user = email_credentials['username']
            pwd = email_credentials['password']

            self.mailer(sender=sender, to=to, subject=subject, text=text, user=user, pwd=pwd)


if __name__ == "__main__":
    vsphere_ops = VsphereOps()
    vsphere_ops.usage(dc_name=dc, cluster_name=cluster)
    vsphere_ops.remove_ocsci_dir()
