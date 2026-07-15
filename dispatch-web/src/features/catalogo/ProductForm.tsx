import { useState, type FormEvent } from 'react'
import { strings } from '../../i18n/strings'
import {
  createProduct,
  replaceComboItems,
  replacePriceTiers,
  updateProduct,
  type ComboItemInput,
  type PriceTierInput,
  type Product,
  type ProductInput,
} from '../../api/catalog'

interface ProductFormProps {
  product?: Product
  allProducts: Product[]
  onSaved: () => void
  onCancel: () => void
}

const inputClass =
  'w-full rounded-md border border-slate-300 px-3 py-1.5 text-sm focus:border-slate-500 focus:outline-none'
const labelClass = 'block text-xs font-medium text-slate-600 mb-1'

export function ProductForm({ product, allProducts, onSaved, onCancel }: ProductFormProps) {
  const [name, setName] = useState(product?.name ?? '')
  const [description, setDescription] = useState(product?.description ?? '')
  const [price, setPrice] = useState(product?.price?.toString() ?? '')
  const [unit, setUnit] = useState(product?.unit ?? '')
  const [imageUrl, setImageUrl] = useState(product?.image_url ?? '')
  const [isCombo, setIsCombo] = useState(product?.is_combo ?? false)
  const [active, setActive] = useState(product?.active ?? true)
  const [comboItems, setComboItems] = useState<ComboItemInput[]>(
    product?.combo_items.map((ci) => ({
      component_product_id: ci.component_product_id,
      quantity: ci.quantity,
    })) ?? [],
  )
  const [priceTiers, setPriceTiers] = useState<PriceTierInput[]>(
    product?.price_tiers.map((pt) => ({ min_quantity: pt.min_quantity, unit_price: pt.unit_price })) ??
      [],
  )
  const [error, setError] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)

  const componentCandidates = allProducts.filter(
    (p) => !p.is_combo && p.id !== product?.id,
  )

  function addComboItem() {
    if (componentCandidates.length === 0) return
    setComboItems((items) => [
      ...items,
      { component_product_id: componentCandidates[0].id, quantity: 1 },
    ])
  }

  function updateComboItem(index: number, patch: Partial<ComboItemInput>) {
    setComboItems((items) => items.map((item, i) => (i === index ? { ...item, ...patch } : item)))
  }

  function removeComboItem(index: number) {
    setComboItems((items) => items.filter((_, i) => i !== index))
  }

  function addPriceTier() {
    setPriceTiers((tiers) => [...tiers, { min_quantity: 1, unit_price: 0 }])
  }

  function updatePriceTier(index: number, patch: Partial<PriceTierInput>) {
    setPriceTiers((tiers) => tiers.map((tier, i) => (i === index ? { ...tier, ...patch } : tier)))
  }

  function removePriceTier(index: number) {
    setPriceTiers((tiers) => tiers.filter((_, i) => i !== index))
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setIsSaving(true)
    try {
      const payload: ProductInput = {
        name,
        description: description || null,
        price: Number(price),
        unit,
        image_url: imageUrl || null,
        is_combo: isCombo,
        active,
      }

      const saved = product
        ? await updateProduct(product.id, payload)
        : await createProduct(payload)

      if (isCombo) {
        await replaceComboItems(saved.id, comboItems)
      }
      await replacePriceTiers(saved.id, priceTiers)

      onSaved()
    } catch {
      setError(strings.catalogo.errorGenerico)
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-4 rounded-lg border border-slate-200 bg-slate-50 p-4"
    >
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={labelClass}>{strings.catalogo.nombre}</label>
          <input
            className={inputClass}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass}>{strings.catalogo.unidad}</label>
          <input
            className={inputClass}
            required
            value={unit}
            onChange={(e) => setUnit(e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass}>{strings.catalogo.precio}</label>
          <input
            className={inputClass}
            required
            type="number"
            min={0}
            value={price}
            onChange={(e) => setPrice(e.target.value)}
          />
        </div>
        <div>
          <label className={labelClass}>{strings.catalogo.imagenUrl}</label>
          <input
            className={inputClass}
            value={imageUrl}
            onChange={(e) => setImageUrl(e.target.value)}
          />
        </div>
        <div className="col-span-2">
          <label className={labelClass}>{strings.catalogo.descripcion}</label>
          <textarea
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
      </div>

      <div className="flex gap-6 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={isCombo} onChange={(e) => setIsCombo(e.target.checked)} />
          {strings.catalogo.esCombolabel}
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" checked={active} onChange={(e) => setActive(e.target.checked)} />
          {strings.catalogo.activo}
        </label>
      </div>

      {isCombo && (
        <div className="rounded-md border border-slate-200 bg-white p-3">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700">
              {strings.catalogo.componentesCombo}
            </span>
            <button
              type="button"
              onClick={addComboItem}
              disabled={componentCandidates.length === 0}
              className="text-xs font-medium text-slate-600 hover:text-slate-900 disabled:opacity-40"
            >
              + {strings.catalogo.agregarComponente}
            </button>
          </div>
          <div className="space-y-2">
            {comboItems.map((item, index) => (
              <div key={index} className="flex items-center gap-2">
                <select
                  className={inputClass}
                  value={item.component_product_id}
                  onChange={(e) =>
                    updateComboItem(index, { component_product_id: Number(e.target.value) })
                  }
                >
                  {componentCandidates.map((candidate) => (
                    <option key={candidate.id} value={candidate.id}>
                      {candidate.name}
                    </option>
                  ))}
                </select>
                <input
                  type="number"
                  min={1}
                  className={`${inputClass} w-24`}
                  value={item.quantity}
                  onChange={(e) => updateComboItem(index, { quantity: Number(e.target.value) })}
                />
                <button
                  type="button"
                  onClick={() => removeComboItem(index)}
                  className="text-xs text-red-600 hover:text-red-800"
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="rounded-md border border-slate-200 bg-white p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-sm font-medium text-slate-700">{strings.catalogo.tramosPrecio}</span>
          <button
            type="button"
            onClick={addPriceTier}
            className="text-xs font-medium text-slate-600 hover:text-slate-900"
          >
            + {strings.catalogo.agregarTramo}
          </button>
        </div>
        <div className="space-y-2">
          {priceTiers.map((tier, index) => (
            <div key={index} className="flex items-center gap-2">
              <span className="text-xs text-slate-500">{strings.catalogo.desde}</span>
              <input
                type="number"
                min={1}
                className={`${inputClass} w-24`}
                value={tier.min_quantity}
                onChange={(e) => updatePriceTier(index, { min_quantity: Number(e.target.value) })}
              />
              <span className="text-xs text-slate-500">{strings.catalogo.precioUnitario}</span>
              <input
                type="number"
                min={0}
                className={`${inputClass} w-28`}
                value={tier.unit_price}
                onChange={(e) => updatePriceTier(index, { unit_price: Number(e.target.value) })}
              />
              <button
                type="button"
                onClick={() => removePriceTier(index)}
                className="text-xs text-red-600 hover:text-red-800"
              >
                &times;
              </button>
            </div>
          ))}
        </div>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={isSaving}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {strings.catalogo.guardar}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="rounded-md px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100"
        >
          {strings.catalogo.cancelar}
        </button>
      </div>
    </form>
  )
}
