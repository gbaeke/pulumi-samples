package main

import (
	"github.com/pulumi/pulumi-azure/sdk/v3/go/azure/containerservice"
	"github.com/pulumi/pulumi-azure/sdk/v3/go/azure/core"
	"github.com/pulumi/pulumi-azure/sdk/v3/go/azure/network"
	appsv1 "github.com/pulumi/pulumi-kubernetes/sdk/v2/go/kubernetes/apps/v1"
	corev1 "github.com/pulumi/pulumi-kubernetes/sdk/v2/go/kubernetes/core/v1"
	metav1 "github.com/pulumi/pulumi-kubernetes/sdk/v2/go/kubernetes/meta/v1"
	"github.com/pulumi/pulumi-kubernetes/sdk/v2/go/kubernetes/providers"
	"github.com/pulumi/pulumi/sdk/v2/go/pulumi"
	"github.com/pulumi/pulumi/sdk/v2/go/pulumi/config"
)

func main() {
	pulumi.Run(func(ctx *pulumi.Context) error {
		// retrieve ssh key, throw error if not set
		sshkey := config.New(ctx, "pulum").Require("sshkey")

		// Create an Azure Resource Group
		resourceGroup, err := core.NewResourceGroup(ctx, "rg-aks-pulumi", &core.ResourceGroupArgs{
			Location: pulumi.String("westeurope"),
		})
		if err != nil {
			return err
		}

		// Create a virtual network
		vnet, err := network.NewVirtualNetwork(ctx, "geba-vnet", &network.VirtualNetworkArgs{
			ResourceGroupName: resourceGroup.Name,
			Location:          resourceGroup.Location,
			AddressSpaces: pulumi.StringArray{
				pulumi.String("10.10.0.0/16"),
			},
		})
		if err != nil {
			return err
		}

		// Create AKS subnet
		subnet, err := network.NewSubnet(ctx, "aks", &network.SubnetArgs{
			AddressPrefix:      pulumi.String("10.10.0.0/24"),
			VirtualNetworkName: vnet.Name,
			ResourceGroupName:  resourceGroup.Name,
		})

		// AKS network arguments
		networkArgs := containerservice.KubernetesClusterNetworkProfileArgs{
			NetworkPlugin:    pulumi.String("azure"),
			DnsServiceIp:     pulumi.String("10.10.1.254"),
			ServiceCidr:      pulumi.String("10.10.1.0/24"),
			DockerBridgeCidr: pulumi.String("172.17.0.1/16"),
		}

		aks, err := containerservice.NewKubernetesCluster(ctx, "aks-pulumi", &containerservice.KubernetesClusterArgs{
			DefaultNodePool: &containerservice.KubernetesClusterDefaultNodePoolArgs{
				Name:         pulumi.String("pulumi"),
				VmSize:       pulumi.String("Standard_DS2_v2"),
				NodeCount:    pulumi.Int(2),
				VnetSubnetId: subnet.ID(),
			},
			DnsPrefix:         pulumi.String("pulumi"),
			ResourceGroupName: resourceGroup.Name,
			Location:          resourceGroup.Location,
			LinuxProfile: &containerservice.KubernetesClusterLinuxProfileArgs{
				AdminUsername: pulumi.String("cluadmin"),
				SshKey: &containerservice.KubernetesClusterLinuxProfileSshKeyArgs{
					KeyData: pulumi.String(sshkey),
				},
			},
			NetworkProfile: networkArgs,
			Identity: &containerservice.KubernetesClusterIdentityArgs{
				Type: pulumi.String("SystemAssigned"),
			},
		}, pulumi.DependsOn([]pulumi.Resource{subnet}))
		if err != nil {
			return err
		}

		// Export the raw kube config.
		ctx.Export("kubeconfig", aks.KubeConfigRaw)

		k8s, err := providers.NewProvider(ctx, "k8sprovider", &providers.ProviderArgs{
			Kubeconfig: aks.KubeConfigRaw,
		}, pulumi.DependsOn([]pulumi.Resource{aks}))
		if err != nil {
			return err
		}

		ns, err := corev1.NewNamespace(ctx, "realtime", &corev1.NamespaceArgs{
			Metadata: &metav1.ObjectMetaArgs{
				Name: pulumi.String("realtime"),
			},
		}, pulumi.Provider(k8s))
		if err != nil {
			return err
		}

		realtimeLabels := pulumi.StringMap{
			"app": pulumi.String("realtimeapp"),
		}

		redisLabels := pulumi.StringMap{
			"app": pulumi.String("realtimeapp"),
		}

		// redis deployment
		redisApp, err := appsv1.NewDeployment(ctx, "redisapp", &appsv1.DeploymentArgs{
			Metadata: &metav1.ObjectMetaArgs{
				Namespace: ns.Metadata.Elem().Name(),
			},
			Spec: appsv1.DeploymentSpecArgs{
				Selector: &metav1.LabelSelectorArgs{
					MatchLabels: redisLabels,
				},
				Replicas: pulumi.Int(1),
				Template: &corev1.PodTemplateSpecArgs{
					Metadata: &metav1.ObjectMetaArgs{
						Labels: redisLabels,
					},
					Spec: &corev1.PodSpecArgs{
						Containers: corev1.ContainerArray{
							corev1.ContainerArgs{
								Name:  pulumi.String("redisapp"),
								Image: pulumi.String("redis:4-32bit"),
								Ports: corev1.ContainerPortArray{
									corev1.ContainerPortArgs{
										ContainerPort: pulumi.Int(6379),
									},
								},
							}},
					},
				},
			},
		}, pulumi.Provider(k8s))
		if err != nil {
			return err
		}

		//redis service
		redisService, err := corev1.NewService(ctx, "redisapp", &corev1.ServiceArgs{
			Metadata: &metav1.ObjectMetaArgs{
				Namespace: ns.Metadata.Elem().Name(),
				Labels:    redisLabels,
				Name:      pulumi.String("redisapp"),
			},
			Spec: &corev1.ServiceSpecArgs{
				Ports: corev1.ServicePortArray{
					corev1.ServicePortArgs{
						Port:       pulumi.Int(6379),
						TargetPort: pulumi.Int(6379),
					},
				},
				Selector: redisLabels,
				Type:     pulumi.String("ClusterIP"),
			},
		}, pulumi.Provider(k8s), pulumi.DependsOn([]pulumi.Resource{redisApp}))
		if err != nil {
			return err
		}

		// realtime deployment
		realtimeApp, err := appsv1.NewDeployment(ctx, "realtimeapp", &appsv1.DeploymentArgs{
			Metadata: &metav1.ObjectMetaArgs{
				Namespace: ns.Metadata.Elem().Name(),
			},
			Spec: appsv1.DeploymentSpecArgs{
				Selector: &metav1.LabelSelectorArgs{
					MatchLabels: realtimeLabels,
				},
				Replicas: pulumi.Int(3),
				Template: &corev1.PodTemplateSpecArgs{
					Metadata: &metav1.ObjectMetaArgs{
						Labels: realtimeLabels,
					},
					Spec: &corev1.PodSpecArgs{
						Containers: corev1.ContainerArray{
							corev1.ContainerArgs{
								Name:  pulumi.String("realtimeapp"),
								Image: pulumi.String("gbaeke/fluxapp:1.0.0"),
								Ports: corev1.ContainerPortArray{
									corev1.ContainerPortArgs{
										ContainerPort: pulumi.Int(8080),
									},
								},
								Env: corev1.EnvVarArray{
									&corev1.EnvVarArgs{
										Name:  pulumi.String("REDISHOST"),
										Value: pulumi.String("redisapp.realtime:6379"),
									},
								},
							}},
					},
				},
			},
		}, pulumi.Provider(k8s), pulumi.DependsOn([]pulumi.Resource{redisService}))
		if err != nil {
			return err
		}

		_, err = corev1.NewService(ctx, "realtimeapp", &corev1.ServiceArgs{
			Metadata: &metav1.ObjectMetaArgs{
				Namespace: ns.Metadata.Elem().Name(),
				Labels:    realtimeLabels,
			},
			Spec: &corev1.ServiceSpecArgs{
				Ports: corev1.ServicePortArray{
					corev1.ServicePortArgs{
						Port:       pulumi.Int(80),
						TargetPort: pulumi.Int(8080),
					},
				},
				Selector: realtimeLabels,
				Type:     pulumi.String("LoadBalancer"),
			},
		}, pulumi.Provider(k8s), pulumi.DependsOn([]pulumi.Resource{realtimeApp}))
		if err != nil {
			return err
		}

		return nil
	})
}
