import pulumi
from pulumi_azure import core, storage, containerservice, network
from pulumi_kubernetes import Provider, yaml
from pulumi_kubernetes.core.v1 import Namespace
from pulumi_kubernetes.helm import v3

# read and set config values
config = pulumi.Config("aks-consul")

sshKey = config.require("sshkey")

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
    linux_profile={"adminUsername": "azure", "ssh_key": {"keyData": sshKey}},
    default_node_pool={
        "name": "pool1",
        "node_count": 3,
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

ns_consul = Namespace("consul",
    opts=pulumi.ResourceOptions(
        depends_on=[aks],
        provider=k8s
    ),
    metadata={
        "name":"consul"
    }
    
)

ns_flux = Namespace("flux",
    opts=pulumi.ResourceOptions(
        depends_on=[aks],
        provider=k8s
    ),
    metadata={
        "name":"flux"
    }
    
)

consul = v3.Chart("consul",
    config=v3.LocalChartOpts(
        path="consul-helm",
        namespace="consul",
        values={
            "connectInject.enabled": "true",
            "client.enabled": "true",
            "client.grpc": "true",
            "syncCatalog.enabled": "true"   
        }        
    ),
    opts=pulumi.ResourceOptions(
        depends_on=[ns_consul],
        provider=k8s
    )    
)

flux = v3.Chart("flux",
    config=v3.LocalChartOpts(
        path="flux",
        namespace="flux",
        values={
            "git.url": "git@github.com:gbaeke/consul-demo",
            "git.path": "config",
            "git.pollInterval": "1m"
        }        
    ),
    opts=pulumi.ResourceOptions(
        depends_on=[ns_flux],
        provider=k8s
    )    
)

