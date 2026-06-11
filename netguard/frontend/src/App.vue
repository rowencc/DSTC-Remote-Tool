<template>
  <el-container>
    <el-aside width="200px">
      <el-menu :default-active="$route.path" router>
        <el-menu-item index="/">
          <span>Dashboard</span>
        </el-menu-item>
        <el-menu-item index="/devices">
          <span>Devices</span>
        </el-menu-item>
        <el-menu-item index="/alerts">
          <span>Alerts</span>
        </el-menu-item>
      </el-menu>
    </el-aside>
    <el-main>
      <router-view />
    </el-main>
  </el-container>
</template>

<script>
export default {
  name: 'App'
}
</script>
