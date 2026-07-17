<script>
  // Subtle Bitcoin ticker — a quiet nod, not a focal point. Deliberately
  // smaller/dimmer than operational tiles per operator request.
  import { items, num, fmt } from '../openhab/index.js';

  const price = $derived(fmt($items.BTC_USD_Price, '', 0));
  const pct = $derived(num($items.BTC_Price_24h_PercentChange));
  const pctText = $derived(pct === null ? '—' : `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`);
  const pctColor = $derived(pct === null ? '#8b93a1' : pct >= 0 ? '#22c55e' : '#ef4444');
</script>

<div class="btc-ticker" title="BTC/USD">
  <span class="glyph">₿</span>
  <span class="price">${price}</span>
  <span class="pct" style="color: {pctColor}">{pctText}</span>
</div>

<style>
  .btc-ticker {
    display: flex;
    align-items: baseline;
    gap: 0.3rem;
    font-size: 0.7rem;
    font-variant-numeric: tabular-nums;
    color: #6b7280;
    opacity: 0.7;
    line-height: 1;
    white-space: nowrap;
  }
  .glyph {
    font-size: 0.75rem;
  }
  .price {
    color: #8b93a1;
  }
  .pct {
    font-size: 0.68rem;
  }
</style>
