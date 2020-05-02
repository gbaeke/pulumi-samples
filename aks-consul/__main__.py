import pulumi
from pulumi_azure import core, storage, containerservice, network
from pulumi_kubernetes import Provider, yaml

# read and set config values
config = pulumi.Config("aks-consul")

SSHKEY = config.require("sshkey")

# create a Resource Group and Network for all resources
rg = core.ResourceGroup("rg-aks-consul")



# create vnet
vnet = network.VirtualNetwork(
    "aks-consul-vnet",
    name="aks-consul-vnet",
    address_spaces=["10.1.0.0/16"],
    resource_group_name=rg.name
)

subnet = network.Subnet(
    "aks-sn",
    opts=pulumi.ResourceOptions(
        depends_on=[vnet]
    ),
    virtual_network_name=vnet.name,
    address_prefixes=["10.1.0.0/24"],
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


realtime = yaml.ConfigFile("realtime",
    opts=pulumi.ResourceOptions(
        depends_on=[aks],
        provider=k8s
    ),
    file_id="realtime.yaml",  
)

pulumi.export("service", realtime.get_resource("v1/Service","realtimeapp").
    apply(lambda svc: svc.status["load_balancer"]["ingress"][0]["ip"])) 