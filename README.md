# vAPP Lease Management

## Overview
A web based application to manage vAPP leases extend requested by users. It provides an interface and API for adding, updating, deleting, and exporting vAPP lease records. User login and API token authentication are both supported.
The application includes a scheduled task that runs daily at 2:00 AM local server time to automatically delete expired vAPPs from the database.

---

## Project Structure

```
application/
│
├── Dockerfile                  # Docker image definition
├── requirements.txt            # Python dependencies
├── vapp_lease_management.py    # Main Flask application
│
├── static/                     # Static files (e.g., images, icons)
│
└── templates/                  # HTML templates for the web UI
    ├── index.html              # Main dashboard
    ├── login.html              # Login page
    ├── usermanagement.html     # User management page
    └── change_password.html    # Change password page
```

---

## API Usage
All API requests require a Bearer token in the header.

---

### List Users

```bash
curl -X GET https://vapplease.xyz.com/api/users \
  -H "Authorization: Bearer <your_token>"
```

---

### Add a vAPP

```bash
curl -X POST https://vapplease.xyz.com/api/add-vapp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_token>" \
  -d '{
    "vappName": "AppDev-TestLab",
    "geo": "EMEA",
    "tenant": "PlatformOps",
    "expiresOn": "30-06-2025",
    "template": "No",
    "ticketID": "DEV99887766"
  }'
```

---

### List vAPPs

```bash
curl "https://vapplease.xyz.com/api/query-vapp" \
  -H "Authorization: Bearer <your_token>"
```

```bash
curl "https://vapplease.xyz.com/api/query-vapp?geo=EMEA&tenant=PlatformOps" \
  -H "Authorization: Bearer <your_token>"
```

---

### Export vAPPs (CSV)

```bash
curl -OJ "https://vapplease.xyz.com/api/export-vapps" \
  -H "Authorization: Bearer <your_token>"
```

```bash
curl -OJ "https://vapplease.xyz.com/api/export-vapps?geo=EMEA&tenant=PlatformOps" \
  -H "Authorization: Bearer <your_token>"
```

---

### Update Lease Expiration

```bash
curl -X PUT https://vapplease.xyz.com/api/update-lease/<vAPP_ID> \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <your_token>" \
  -d '{"expiresOn": "15-07-2025"}'
```

---

### Delete a vAPP

```bash
curl -X DELETE https://vapplease.xyz.com/api/delete-vapp/<vAPP_ID> \
  -H "Authorization: Bearer <your_token>"
```

---

### Clean Expired vAPPs

```bash
curl -X DELETE https://vapplease.xyz.com/api/clean-expired-vapps \
  -H "Authorization: Bearer <your_token>"
```

---

## Kubernetes Deployment

This project includes Kubernetes manifests for deploying the application, database, and handling backups.

### Files located in `k8s-files/`:

```
k8s-files/
├── backup_pg_db.sh                # Script to run a pg_dump backup as a Kubernetes Job
├── db-backup-pvc.yaml             # PVC for storing database backups (NFS)
├── db-pvc.yaml                    # PVC for the Postgres database storage (NFS)
├── db-service.yaml                # LoadBalancer service exposing Postgres
├── vapp-db-secret.yaml            # Base64 encoded secrets for DB credentials
├── vapp-lease-deployment.yaml     # Deployment definition for the Flask app
└── vapp-lease-service.yaml        # LoadBalancer service exposing the Flask app on port 80
```

### Prerequisites

- Kubernetes cluster access (with `kubectl` configured)
- Helm installed
- NFS storage provisioned and accessible

---

### Step-by-step Deployment

1. **Clone the repository:**

```bash
git clone https://<GitHub_URL>/vapp-lease-management.git
cd vapp-lease-management/K8s
```

2. **Create a dedicated Kubernetes namespace:**

```bash
kubectl create namespace vapp-lease
```

3. **Create NFS Persistent Volume Claims (PVCs):**

```bash
kubectl apply -f db-pvc.yaml -n vapp-lease
kubectl apply -f db-backup-pvc.yaml -n vapp-lease
```

4. **Add the Bitnami Helm repository and update:**

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

5. **Deploy PostgreSQL using Helm:**

```bash
helm install postgres bitnami/postgresql \
  --namespace vapp-lease \
  --set global.postgresql.auth.username=vapp_user \
  --set global.postgresql.auth.database=vapp_db \
  --set persistence.enabled=true \
  --set persistence.existingClaim=postgres-nfs-pvc \
  --set service.type=LoadBalancer
```

6. **Retrieve the PostgreSQL password:**

```bash
kubectl get secret --namespace vapp-lease postgres-postgresql \
  -o jsonpath="{.data.postgres-password}" | base64 --decode
```

7. **Log in to PostgreSQL:**

```bash
kubectl exec -it postgres-postgresql-0 -n vapp-lease -- psql -U postgres
```

8. **Set password for `vapp_user`:**

```sql
ALTER USER vapp_user WITH PASSWORD '<PASSWORD>';
```

9. **Create application's database secret:**

```bash
kubectl apply -f vapp-db-secret.yaml -n vapp-lease
```

10. **Deploy the vAPP Lease Management application:**

```bash
kubectl apply -f vapp-lease-deployment.yaml -n vapp-lease
```

11. **Expose the application using a LoadBalancer service:**

```bash
kubectl apply -f vapp-lease-service.yaml -n vapp-lease
```

12. **Get the external IP and update DNS records accordingly:**

```bash
kubectl get service vapp-lease-service -n vapp-lease
```

---

## Application Information
- **Application Name:** vAPP Lease Management
- **Version:** 1.0
- **Author:** George Gabra
- **Creation Date:** May 28, 2025, 11:03 AM
