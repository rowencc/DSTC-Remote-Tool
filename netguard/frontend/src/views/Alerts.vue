<template>
  <div>
    <el-table :data="alerts" style="width: 100%">
      <el-table-column prop="severity" label="Severity">
        <template #default="{ row }">
          <el-tag :type="getSeverityType(row.severity)">
            {{ row.severity }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="alert_type" label="Type" />
      <el-table-column prop="message" label="Message" />
      <el-table-column prop="created_at" label="Time" />
      <el-table-column label="Actions">
        <template #default="{ row }">
          <el-button
            v-if="!row.acknowledged"
            size="small"
            @click="acknowledgeAlert(row.id)"
          >
            Acknowledge
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script>
import api from '@/api'

export default {
  data() {
    return {
      alerts: []
    }
  },
  mounted() {
    this.loadAlerts()
  },
  methods: {
    async loadAlerts() {
      const res = await api.get('/alerts/')
      this.alerts = res.data
    },
    async acknowledgeAlert(id) {
      await api.put(`/alerts/${id}/ack`)
      await this.loadAlerts()
    },
    getSeverityType(severity) {
      const types = {
        'INFO': 'info',
        'WARNING': 'warning',
        'CRITICAL': 'danger'
      }
      return types[severity] || 'info'
    }
  }
}
</script>