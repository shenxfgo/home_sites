import { createApp } from 'vue'
import {
  ElBadge,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElColorPicker,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDivider,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElLoading,
  ElOption,
  ElPageHeader,
  ElPagination,
  ElPopover,
  ElProgress,
  ElScrollbar,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
} from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import router from './router'
import App from './App.vue'
import './styles/global.css'
import './styles/glass.css'

// 只注册模板里真正用到的组件：app.use(ElementPlus) 会引用全部组件，
// tree-shaking 完全失效，入口 chunk 因此多出约 600 kB。
const components = [
  ElBadge,
  ElButton,
  ElCard,
  ElCheckbox,
  ElCheckboxGroup,
  ElColorPicker,
  ElDescriptions,
  ElDescriptionsItem,
  ElDialog,
  ElDivider,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElIcon,
  ElInput,
  ElInputNumber,
  ElOption,
  ElPageHeader,
  ElPagination,
  ElPopover,
  ElProgress,
  ElScrollbar,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTag,
]

const app = createApp(App)

// 图标由各组件按需从 @element-plus/icons-vue 引入，这里不做全局注册，
// 否则 293 个图标组件会全部打进入口 chunk。
for (const component of components) {
  app.use(component)
}

// 各视图用 v-loading 指令显示骨架，它随 ElLoading 插件注册而非组件
app.use(ElLoading)

app.use(router)
app.mount('#app')
