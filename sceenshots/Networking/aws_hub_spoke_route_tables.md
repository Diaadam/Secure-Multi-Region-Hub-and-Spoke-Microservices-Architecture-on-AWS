# AWS Hub-and-Spoke Centralized Inspection Route Tables

This document contains the complete, master routing configuration for a Hub-and-Spoke architecture using an **API Gateway VPC Link**, **Internal Application Load Balancer**, **AWS Network Firewall (Multi-AZ)**, and **AWS Transit Gateway (TGW)**.

This design ensures 100% symmetric firewall inspection for inbound, outbound, and return traffic.

---

## 1. FW-SPOKE-VPC Route Tables (`10.20.0.0/16`)

The Spoke VPC relies entirely on the Hub for security, routing, and internet access. It remains isolated and simple.

### A. Spoke ECS Workload Subnets
**Attached to:** `10.20.0.0/24` & `10.20.1.0/24`

| Destination | Target | Purpose |
| :--- | :--- | :--- |
| `10.20.0.0/16` | `local` | Allows internal communication across Spoke subnets. |
| `0.0.0.0/0` | `Transit Gateway (tgw-id)` | Sends all egress traffic (to the internet) AND all return traffic (back to API Gateway) to the Hub. |

### B. Spoke TGW Attachment Subnets
**Attached to:** `10.20.2.0/24` & `10.20.3.0/24`

| Destination | Target | Purpose |
| :--- | :--- | :--- |
| `10.20.0.0/16` | `local` | Allows the Transit Gateway to drop incoming Hub traffic into the Spoke and reach the ECS tasks. |

---

## 2. FW-HUB-VPC Route Tables (`10.10.0.0/16`)

The Hub acts as the central routing and inspection engine. It intercepts traffic moving in any direction and forces it through the security layer.

*Note: For the Hub VPC, you must maintain separate route tables for AZ-A and AZ-B to ensure traffic always targets the `vpce` (VPC Endpoint) of the Firewall in its respective Availability Zone. This is referred to below as `vpce-Firewall-AZ`.*

### A. API Gateway VPC Link Subnets (Ingress Entry)
**Attached to:** The specific subnets mapped to your API Gateway VPC Link.

| Destination | Target | Purpose |
| :--- | :--- | :--- |
| `10.10.0.0/16` | `local` | Allows the API Gateway VPC Link ENIs to natively forward user requests to the Internal Load Balancer. |

### B. Internal Load Balancer (ALB/NLB) Subnets
**Attached to:** `10.10.3.0/24` & `10.10.5.0/24`

| Destination | Target | Purpose |
| :--- | :--- | :--- |
| `10.10.0.0/16` | `local` | Internal Hub communication (e.g., returning responses to the API GW Link). |
| `10.20.0.0/16` | `vpce-Firewall-AZ` | **Forced Inbound Inspection:** Intercepts traffic headed to the Spoke ECS and pushes it to the Firewall. |

### C. Hub TGW Attachment Subnets
**Attached to:** `10.10.0.0/24` & `10.10.4.0/24`

| Destination | Target | Purpose |
| :--- | :--- | :--- |
| `10.10.0.0/16` | `local` | Internal Hub communication. |
| `0.0.0.0/0` | `vpce-Firewall-AZ` | **Forced Egress & Return Inspection:** Catches all traffic leaving the Spoke (whether going to the internet or returning to the ALB) and forces it to the Firewall. |

### D. Firewall Subnets
**Attached to:** `10.10.1.0/24` & `10.10.6.0/24`

| Destination | Target | Purpose |
| :--- | :--- | :--- |
| `10.10.0.0/16` | `local` | Routes safe return traffic back to the Internal Load Balancer natively. |
| `10.20.0.0/16` | `Transit Gateway (tgw-id)` | Routes safe inbound traffic down to the Spoke VPC via TGW. |
| `0.0.0.0/0` | `NAT Gateway (nat-id)` | Routes safe outbound internet traffic (from the Spoke) to the NAT Gateway. |

### E. Public / NAT Gateway Subnets
**Attached to:** `10.10.2.0/24`

| Destination | Target | Purpose |
| :--- | :--- | :--- |
| `10.10.0.0/16` | `local` | Internal Hub communication. |
| `0.0.0.0/0` | `Internet Gateway (igw-id)` | Sends the translated outbound traffic out to the public internet. |

---

## 3. Traffic Flow Summary

1. **Inbound Flow:** API Gateway → VPC Link → Internal ALB → **Firewall (AZ Specific)** → Transit Gateway → ECS
2. **Outbound Flow:** ECS → Transit Gateway → **Firewall (AZ Specific)** → NAT Gateway → Internet Gateway → Internet
3. **Return Paths:** Both inbound and outbound return traffic are forced back through the exact same **Firewall VPCE** for stateful, symmetric inspection before reaching their final destination.
