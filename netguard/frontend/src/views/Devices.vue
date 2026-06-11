<template>
  <div>
    <el-button type="primary" @click="scanNetwork" :loading="scanning">
      Scan Network
    </el-button>
    <el-table :data="devices" style="width: 100%">
      <el-table-column prop="mac_address" label="MAC Address" />
      <el-table-column prop="vendor" label="Vendor" />
      <el-table-column prop="device_type" label="Type" />
      <el-table-column prop="ip_address" label="IP Address" />
      <el-table-column prop="risk_level" label="Risk">
        <template #default="{ row }">
          <el-tag :type="getRiskType(row.risk_level)">
            {{ row.risk_level }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="last_seen" label="Last Seen" />
    </el-table>
  </div>
</template>

<script>
import api from '@/api'

export default {
  data() {
    return {
      devices: [],
      scanning: false
    }
  },
  mounted() {
    this.loadDevices()
  },
  methods: {
    async loadDevices() {
      const res = await api.get('/devices/')
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
      const types = {
        'LOW': 'success',
        'MEDIUM': 'warning',
        'HIGH': 'danger',
        'CRITICAL': 'danger'
      }
      return types[risk] || 'info'
    }
  }
}
</script>