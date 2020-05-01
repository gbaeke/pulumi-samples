import pulumi
from pulumi_azure import core, storage, containerservice, network
from pulumi_azuread import Application, ServicePrincipal, ServicePrincipalPassword
from pulumi_kubernetes import Provider, yaml

# read and set config values
config = pulumi.Config("kub-python")

PASSWORD = config.require_secret("password")
SSHKEY = config.require("sshkey")

# create a Resource Group and Network for all resources
rg = core.ResourceGroup("rg-pul-aks")



# create vnet
vnet = network.VirtualNetwork(
    "pul-aks-vnet",
    name="pul-aks-vnet",
    address_spaces=["10.1.0.0/16"],
    resource_group_name=rg.name
)

subnet = network.Subnet(
    "aks-sn",
    opts=pulumi.ResourceOptions(
        depends_on=[vnet]
    ),
    virtual_network_name=vnet.name,
    address_prefix="10.1.0.0/24",
    resource_group_name=rg.name
)

aks = containerservice.KubernetesCluster(
    "aksCluster",
    opts=pulumi.ResourceOptions(
        depends_on=[subnet]
    ),
    resource_group_name=rg.name,
    dns_prefix="pul",
    linux_profile={"adminUsername": "azure", "ssh_key": {"keyData": SSHKEY}},
    default_node_pool={
        "name": "pool1",
        "node_count": 2,
        "vm_size": "Standard_B2ms",
        "vnet_subnet_id": subnet.id
    },
    network_profile={
        "networkPlugin": "azure",
        "dnsServiceIp": "10.10.1.254",
        "dockerBridgeCidr": "172.17.0.1/16",
        "serviceCidr": "10.10.1.0/24"
    },
    identity={
        "type": "SystemAssigned"
    }
)

k8s = Provider(
    "k8s", kubeconfig=aks.kube_config_raw,
)

#realtime = yaml.ConfigFile('realtime', 'realtime.yaml')

