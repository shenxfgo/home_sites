import axios from 'axios'

/** Axios instance pre-configured with base URL and JSON headers. */
const client = axios.create({
  baseURL: '/api',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
})

/** Global error interceptor – surfaces a readable message on network / server errors. */
client.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ?? error.message ?? 'Unknown error'
    return Promise.reject(new Error(message))
  },
)

export default client
