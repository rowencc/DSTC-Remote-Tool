<template>
  <div>
    <h1>NetGuard Dashboard</h1>
    <el-row :gutter="20">
      <el-col :span="8">
        <el-card>
          <template #header>Total Devices</template>
          <div class="stat-number">{{ stats.device_count }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>Unacknowledged Alerts</template>
          <div class="stat-number warning">{{ stats.unacknowledged_alerts }}</div>
        </el-card>
      </el-col>
      <el-col :span="8">
        <el-card>
          <template #header>Risk Devices</template>
          <div class="stat-number danger">{{ stats.risk_devices }}</div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<script>
import api from '@/api'

export default {
  data() {
    return {
      stats: {
        device_count: 0,
        unacknowledged_alerts: 0,
        risk_devices: 0
      }
    }
  },
  mounted() {
    this.loadStats()
  },
  methods: {
    async loadStats() {
      const res = await api.get('/system/stats')
      this.stats = res.data
    }
  }
}
</script>

<style scoped>
.stat-number {
  font-size: 48px;
  font-weight: bold;
  text-align: center;
}
.warning { color: #e6a23c; }
.danger { color: #f56c6c; }
</style>