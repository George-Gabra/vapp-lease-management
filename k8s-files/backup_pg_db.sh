#!/bin/bash

# === CONFIG ===
NAMESPACE="vapp-lease"
DB_USER="vapp_user"
DB_NAME="vapp_db"
PVC_NAME="postgres-backup-nfs-pvc"
JOB_NAME="pg-backup-job-$(date +%Y%m%d%H%M%S)"
BACKUP_FILE="vapp_db_backup_$(date +%Y%m%d_%H%M%S).sql"
BACKUP_DIR="/backup"

# === FUNCTIONS ===
log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# === START ===
log "Fetching DB password from Kubernetes secret..."
DB_PASSWORD=$(kubectl get secret --namespace $NAMESPACE postgres-postgresql -o jsonpath="{.data.password}" | base64 --decode)

# === GENERATE JOB YAML ===
log "Generating Kubernetes Job manifest..."

cat <<EOF > pg_backup_job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: ${JOB_NAME}
  namespace: ${NAMESPACE}
spec:
  template:
    spec:
      securityContext:
        runAsUser: 0
        runAsGroup: 0
      containers:
      - name: pg-backup
        image: bitnami/postgresql:17.2.0-debian-12-r10
        env:
        - name: PGPASSWORD
          valueFrom:
            secretKeyRef:
              name: postgres-postgresql
              key: password
        command: ["/bin/bash", "-c"]
        args:
        - |
          set -e
          log() { echo "[\$(date '+%Y-%m-%d %H:%M:%S')] \$1"; }
          log "Starting PostgreSQL backup..."
          pg_dump -h postgres-postgresql -U ${DB_USER} ${DB_NAME} > ${BACKUP_DIR}/${BACKUP_FILE}
          log "Backup created: ${BACKUP_FILE}"
          log "Existing backups:"
          ls -lh ${BACKUP_DIR}
          log "Deleting backups older than 30 days:"
          find ${BACKUP_DIR} -name '*.sql' -type f -mtime +30 -print -delete
          log "Cleanup complete."
        volumeMounts:
        - name: backup-vol
          mountPath: ${BACKUP_DIR}
      volumes:
      - name: backup-vol
        persistentVolumeClaim:
          claimName: ${PVC_NAME}
      restartPolicy: Never
  backoffLimit: 1
EOF

# === EXECUTE JOB ===
log "Launching backup job: ${JOB_NAME}"
kubectl apply -f pg_backup_job.yaml

log "Waiting for job to complete..."
kubectl wait --for=condition=complete job/${JOB_NAME} --namespace ${NAMESPACE} --timeout=180s

log "Backup job completed. Logs:"
kubectl logs job/${JOB_NAME} -n ${NAMESPACE}

log "Cleaning up job..."
kubectl delete job ${JOB_NAME} -n ${NAMESPACE}
rm -f pg_backup_job.yaml

log "Backup process completed successfully!"

