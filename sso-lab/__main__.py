import pulumi
from pulumi import Config, ResourceOptions, Output
from pulumi_azure import core, storage, compute, network, sql

config=Config("sso-lab")


# retrieve password from config
pwd = config.require_secret("pwd")
sqlpwd = config.require_secret("sqlpwd")
print("Secrets retrieved...")

# set some vars
server_user="azadmin"
sql_user="azadmin"

# Create an Azure Resource Group
rg = core.ResourceGroup("rg-ssolab")

# create vnet
vnet = network.VirtualNetwork(
    "vnet-sso",
    address_spaces=["10.2.0.0/16"],
    resource_group_name=rg.name
)

subnet = network.Subnet(
    "servers",
    virtual_network_name=vnet.name,
    address_prefix="10.2.0.0/24",
    resource_group_name=rg.name
)

bastionSubnet = network.Subnet(
    "bastion",
    name="AzureBastionSubnet",
    virtual_network_name=vnet.name,
    address_prefix="10.2.1.0/24",
    resource_group_name=rg.name
    
) 

# public ip
ip = network.PublicIp("geba-sso-ip",
    resource_group_name=rg.name,
    allocation_method="Static",
    sku="Standard"   
)

# create bastion
bastion = compute.BastionHost("sso-bastion",
    resource_group_name=rg.name,
    ip_configuration={
        "name": "ipconfig1",
        "publicIpAddressId": ip.id,
        "subnet_id": bastionSubnet.id
    }
)

img2019 = { 
    "offer": "WindowsServer",
    "publisher": "MicrosoftWindowsServer",
    "sku": "2019-Datacenter",
    "version": "latest"
    }

vm_config = []
vm_config.append({"name": "vm-dc", "img": img2019, "size": "Standard_B2ms"})
vm_config.append({"name": "vm-adc", "img": img2019, "size": "Standard_B2ms"})

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
        admin_username=server_user,
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

# create azure sql server
sqlserver = sql.SqlServer("sso-sql",
    resource_group_name=rg.name,
    administrator_login="gbaeke",
    administrator_login_password=sqlpwd,
    version="12.0"
)

# create sql database
sqldb = sql.Database("sso-db",
    resource_group_name=rg.name,
    server_name=sqlserver.name,
    edition="Standard",
    requested_service_objective_name="S1"
)

# connection string (thanks Pulumi docs)
connection_string = Output.all(sqlserver.name, sqldb.name, sql_user, sqlpwd) \
    .apply(lambda args: f"Server=tcp:{args[0]}.database.windows.net;initial catalog={args[1]};user ID={args[2]};password={args[3]};Min Pool Size=0;Max Pool Size=30;Persist Security Info=true;")



# Export the connection string for the storage account
pulumi.export('vm_ids', vm_ids)
pulumi.export('connstr', connection_string)
