<template>
  <div>
    <div style="margin-bottom: 16px; display: flex; align-items: center; gap: 12px;">
      <el-button type="primary" @click="scanNetwork" :loading="scanning">
        {{ scanning ? 'Scanning...' : 'Scan Network' }}
      </el-button>
      <el-button @click="loadDevices">Refresh</el-button>
      <el-select v-model="filterRisk" placeholder="Filter Risk" clearable @change="loadDevices" style="width: 140px;">
        <el-option label="All" value="" />
        <el-option label="HIGH" value="HIGH" />
        <el-option label="MEDIUM" value="MEDIUM" />
        <el-option label="LOW" value="LOW" />
      </el-select>
      <span style="color: #909399;">{{ devices.length }} devices</span>
    </div>

    <el-table :data="devices" style="width: 100%" stripe border>
      <el-table-column prop="ip_address" label="IP Address" width="140" />
      <el-table-column prop="mac_address" label="MAC Address" width="180" />
      <el-table-column prop="hostname" label="Device Name" min-width="160">
        <template #default="{ row }">
          <span v-if="row.hostname" style="font-weight: 500;">{{ row.hostname }}</span>
          <span v-else style="color: #C0C4CC;">--</span>
        </template>
      </el-table-column>
      <el-table-column prop="vendor" label="Vendor" min-width="120">
        <template #default="{ row }">
          <span v-if="row.vendor">{{ row.vendor }}</span>
          <span v-else style="color: #C0C4CC;">--</span>
        </template>
      </el-table-column>
      <el-table-column prop="device_type" label="Device Type" width="120">
        <template #default="{ row }">
          <el-tag :type="getDeviceTypeTag(row.device_type)" size="small">
            {{ getDeviceTypeIcon(row.device_type) }} {{ row.device_type }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="risk_level" label="Risk" width="100">
        <template #default="{ row }">
          <el-tag :type="getRiskType(row.risk_level)" size="small" effect="dark">
            {{ row.risk_level }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="is_authorized" label="Status" width="100">
        <template #default="{ row }">
          <el-tag v-if="row.is_authorized" type="success" size="small">Authorized</el-tag>
          <el-tag v-else type="info" size="small">Unknown</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_seen" label="Last Seen" width="180" />
    </el-table>
  </div>
</template>

<script>
import api from '@/api'

export default {
  data() {
    return {
      devices: [],
      scanning: false,
      filterRisk: ''
    }
  },
  mounted() {
    this.loadDevices()
  },
  methods: {
    async loadDevices() {
      const params = this.filterRisk ? { risk_level: this.filterRisk } : {}
      const res = await api.get('/devices/', { params })
      this.devices = res.data
    },
    async scanNetwork() {
      this.scanning = true
      try {
        await api.post('/devices/scan')
        await this.loadDevices()
      } finally {
        this.scanning = false
      }
    },
    getRiskType(risk) {
      const types = { 'LOW': 'success', 'MEDIUM': 'warning', 'HIGH': 'danger', 'CRITICAL': 'danger' }
      return types[risk] || 'info'
    },
    getDeviceTypeTag(type) {
      const types = { 'camera': 'danger', 'router': '', 'phone': 'success', 'computer': 'warning', 'iot': 'info' }
      return types[type] || 'info'
    },
    getDeviceTypeIcon(type) {
      const icons = { 'camera': '📹', 'router': '🌐', 'phone': '📱', 'computer': '💻', 'iot': '📡' }
      return icons[type] || '❓'
    }
  }
}
</script>
