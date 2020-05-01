import pulumi
from pulumi import Config, ResourceOptions
from pulumi_azure import core, storage, compute, network

config=Config("vms-python")


# retrieve password from config
pwd = config.require_secret("pwd")
print("Secret retrieved...")

# Create an Azure Resource Group
rg = core.ResourceGroup("rg-geba-vm-pulumi",
    name="rg-geba-vm-pulumi"
    )

# create vnet
vnet = network.VirtualNetwork(
    "pul-vm-vnet",
    name="pul-vm-vnet",
    address_spaces=["10.2.0.0/16"],
    resource_group_name=rg.name
)

subnet = network.Subnet(
    "vm-sn",
    opts=pulumi.ResourceOptions(
        depends_on=[vnet]
    ),
    virtual_network_name=vnet.name,
    address_prefix="10.2.0.0/24",
    resource_group_name=rg.name
)

img2019 = { 
    "offer": "WindowsServer",
    "publisher": "MicrosoftWindowsServer",
    "sku": "2019-Datacenter",
    "version": "latest"
    }

img2012 = { 
    "offer": "WindowsServer",
    "publisher": "MicrosoftWindowsServer",
    "sku": "2012-Datacenter",
    "version": "3.127.20180613"
    }

vm_config = []
vm_config.append({"name": "vm001", "img": img2019, "size": "Standard_B2ms"})
vm_config.append({"name": "vm002", "img": img2012, "size": "Standard_F2"})

vm_ids = []
for config in vm_config:

    nic = network.NetworkInterface(config["name"]+"nic",
        name=config["name"]+"nic",
        resource_group_name=rg.name,
        ip_configurations=[
            {
                "name": "ipconfig1",
                "privateIpAddressAllocation": "Dynamic",
                "subnet_id": subnet.id
            }
        ]
    )

    vm = compute.WindowsVirtualMachine(config["name"],
        opts=pulumi.ResourceOptions(
            depends_on=[nic]
        ),
        resource_group_name=rg.name,
        location=rg.location,
        admin_username="gbaeke",
        admin_password=pwd,
        name=config["name"],
        network_interface_ids=[nic.id],
        os_disk={
            "caching": "None",
            "storage_account_type": "Standard_LRS"
        },
        size= config["size"],
        source_image_reference=config["img"]
    )
    vm_ids.append(vm.id)



# Export the connection string for the storage account
pulumi.export('vm_names', vm_ids)
