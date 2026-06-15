<template>
  <div class="restocking-view">
    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Page header -->
      <div class="page-header">
        <h2>{{ t('restocking.title') }}</h2>
        <p>{{ t('restocking.description') }}</p>
      </div>

      <!-- Budget slider -->
      <div class="card budget-card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budgetLabel') }}</h3>
        </div>
        <div class="budget-controls">
          <input
            type="range"
            min="0"
            max="50000"
            step="100"
            v-model.number="budgetLimit"
            class="budget-slider"
          />
          <span class="budget-value">{{ currencySymbol }}{{ budgetLimit.toLocaleString() }}</span>
        </div>
      </div>

      <!-- Summary stat cards -->
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.recommendedItems') }}</div>
          <div class="stat-value">{{ restockingRecommendations.length }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.estimatedCost') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ estimatedCost.toLocaleString() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ currencySymbol }}{{ remainingBudget.toLocaleString() }}</div>
        </div>
      </div>

      <!-- Recommendations table -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.title') }}</h3>
          <button
            class="place-order-btn"
            :disabled="restockingRecommendations.length === 0 || submitting || orderSuccess"
            @click="placeRestockingOrder"
          >
            {{ submitting ? t('common.loading') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="orderSuccess" class="success-banner">
          {{ t('restocking.orderPlaced') }}
        </div>
        <div v-if="orderError" class="error-banner">
          {{ orderError }}
        </div>

        <div v-if="restockingRecommendations.length === 0" class="empty-state">
          <p>{{ t('restocking.noRecommendations') }}</p>
        </div>
        <div v-else class="table-container">
          <table class="restocking-table">
            <thead>
              <tr>
                <th>{{ t('restocking.itemName') }}</th>
                <th>{{ t('restocking.sku') }}</th>
                <th>{{ t('restocking.trend') }}</th>
                <th>{{ t('restocking.forecastedDemand') }}</th>
                <th>{{ t('restocking.unitCost') }}</th>
                <th>{{ t('restocking.recommendedQty') }}</th>
                <th>{{ t('restocking.totalCost') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in restockingRecommendations" :key="item.id">
                <td>{{ item.item_name }}</td>
                <td class="sku-cell">{{ item.item_sku }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td>{{ item.forecasted_demand.toLocaleString() }}</td>
                <td>
                  <span v-if="item.unit_cost === 0" class="no-cost-note">{{ t('restocking.noCostData') }}</span>
                  <span v-else>{{ currencySymbol }}{{ item.unit_cost.toLocaleString() }}</span>
                </td>
                <td>{{ item.recommended_qty.toLocaleString() }}</td>
                <td>
                  <span v-if="item.total_cost === 0" class="no-cost-note">—</span>
                  <span v-else>{{ currencySymbol }}{{ item.total_cost.toLocaleString() }}</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'

// Priority order for greedy fill: lower number = higher priority
const TREND_PRIORITY = { increasing: 0, stable: 1, decreasing: 2 }

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency } = useI18n()

    const currencySymbol = computed(() => currentCurrency.value === 'JPY' ? '¥' : '$')

    const loading = ref(true)
    const error = ref(null)
    const allForecasts = ref([])
    const inventoryItems = ref([])
    const budgetLimit = ref(25000)
    const submitting = ref(false)
    const orderSuccess = ref(false)
    const orderError = ref(null)

    // Map SKU -> unit_cost for O(1) lookup during recommendation computation
    const inventoryCostBySkuMap = computed(() => {
      const map = {}
      for (const item of inventoryItems.value) {
        map[item.sku] = item.unit_cost
      }
      return map
    })

    // Greedy fill: sort by trend priority, include items whose total cost fits within remaining budget
    const restockingRecommendations = computed(() => {
      const sorted = [...allForecasts.value].sort(
        (a, b) => (TREND_PRIORITY[a.trend] ?? 99) - (TREND_PRIORITY[b.trend] ?? 99)
      )

      let remainingBudgetValue = budgetLimit.value
      const recommended = []

      for (const forecast of sorted) {
        const unitCost = inventoryCostBySkuMap.value[forecast.item_sku] ?? 0
        const recommendedQty = forecast.forecasted_demand
        const totalCost = unitCost * recommendedQty

        if (totalCost <= remainingBudgetValue) {
          recommended.push({
            id: forecast.id,
            item_sku: forecast.item_sku,
            item_name: forecast.item_name,
            trend: forecast.trend,
            forecasted_demand: forecast.forecasted_demand,
            unit_cost: unitCost,
            recommended_qty: recommendedQty,
            total_cost: totalCost,
          })
          remainingBudgetValue -= totalCost
        }
      }

      return recommended
    })

    const estimatedCost = computed(() =>
      restockingRecommendations.value.reduce((sum, item) => sum + item.total_cost, 0)
    )

    const remainingBudget = computed(() =>
      Math.max(0, budgetLimit.value - estimatedCost.value)
    )

    const loadData = async () => {
      try {
        loading.value = true
        error.value = null
        // Fetch forecasts and inventory in parallel
        const [forecasts, inventory] = await Promise.all([
          api.getDemandForecasts(),
          api.getInventory(),
        ])
        allForecasts.value = forecasts
        inventoryItems.value = inventory
      } catch (err) {
        error.value = t('common.error')
        console.error('Failed to load restocking data:', err)
      } finally {
        loading.value = false
      }
    }

    const placeRestockingOrder = async () => {
      submitting.value = true
      orderError.value = null

      const now = new Date()
      const orderDate = now.toISOString().slice(0, 19)

      const delivery = new Date(now)
      delivery.setDate(delivery.getDate() + 14)
      const expectedDelivery = delivery.toISOString().slice(0, 10)

      // RST prefix distinguishes restocking orders from customer orders (ORD prefix)
      const orderNumber = `RST-${now.getFullYear()}-${String(now.getTime()).slice(-4).padStart(4, '0')}`

      const orderPayload = {
        order_number: orderNumber,
        customer: 'Internal Restocking',
        items: restockingRecommendations.value.map(item => ({
          sku: item.item_sku,
          name: item.item_name,
          quantity: item.recommended_qty,
          unit_price: item.unit_cost,
        })),
        status: 'Processing',
        order_date: orderDate,
        expected_delivery: expectedDelivery,
        total_value: estimatedCost.value,
        warehouse: null,
        category: null,
      }

      try {
        await api.submitRestockingOrder(orderPayload)
        orderSuccess.value = true
      } catch (err) {
        orderError.value = t('restocking.orderFailed')
        console.error('Failed to submit restocking order:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(loadData)

    return {
      t,
      currencySymbol,
      loading,
      error,
      budgetLimit,
      submitting,
      orderSuccess,
      orderError,
      restockingRecommendations,
      estimatedCost,
      remainingBudget,
      placeRestockingOrder,
    }
  }
}
</script>

<style scoped>
.restocking-view {
  padding: 1.5rem;
}

.budget-card {
  margin-bottom: 1.5rem;
}

.budget-controls {
  display: flex;
  align-items: center;
  gap: 1.5rem;
  padding: 0.5rem 0;
}

.budget-slider {
  flex: 1;
  height: 6px;
  cursor: pointer;
  accent-color: #2563eb;
}

.budget-value {
  font-size: 1.25rem;
  font-weight: 700;
  color: #0f172a;
  min-width: 120px;
  text-align: right;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.place-order-btn {
  background: #2563eb;
  color: #fff;
  border: none;
  border-radius: 6px;
  padding: 0.5rem 1.25rem;
  font-size: 0.875rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.place-order-btn:hover:not(:disabled) {
  background: #1d4ed8;
}

.place-order-btn:disabled {
  background: #94a3b8;
  cursor: not-allowed;
}

.success-banner {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  border-radius: 6px;
  color: #15803d;
  font-size: 0.875rem;
  font-weight: 500;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.error-banner {
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  color: #dc2626;
  font-size: 0.875rem;
  font-weight: 500;
  padding: 0.75rem 1rem;
  margin-bottom: 1rem;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.9rem;
}

.table-container {
  overflow-x: auto;
}

.restocking-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.875rem;
}

.restocking-table th {
  text-align: left;
  padding: 0.75rem 1rem;
  background: #f8fafc;
  color: #64748b;
  font-weight: 600;
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-bottom: 1px solid #e2e8f0;
}

.restocking-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid #f1f5f9;
  color: #334155;
}

.restocking-table tr:last-child td {
  border-bottom: none;
}

.restocking-table tr:hover td {
  background: #f8fafc;
}

.sku-cell {
  font-family: monospace;
  font-size: 0.8rem;
  color: #64748b;
}

.no-cost-note {
  color: #94a3b8;
  font-size: 0.8rem;
  font-style: italic;
}
</style>
