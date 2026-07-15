import { Fragment, useEffect, useState } from 'react'
import { strings } from '../../i18n/strings'
import { listProducts, updateProduct, type Product } from '../../api/catalog'
import { ProductForm } from './ProductForm'

export function ProductsSection() {
  const [products, setProducts] = useState<Product[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [editingId, setEditingId] = useState<number | 'new' | null>(null)

  async function reload() {
    const page = await listProducts()
    setProducts(page.items)
  }

  useEffect(() => {
    setIsLoading(true)
    reload().finally(() => setIsLoading(false))
  }, [])

  async function handleToggleActive(product: Product) {
    await updateProduct(product.id, { active: !product.active })
    await reload()
  }

  function handleSaved() {
    setEditingId(null)
    void reload()
  }

  if (isLoading) return null

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <button
          onClick={() => setEditingId('new')}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700"
        >
          {strings.catalogo.nuevoProducto}
        </button>
      </div>

      {editingId === 'new' && (
        <ProductForm
          allProducts={products}
          onSaved={handleSaved}
          onCancel={() => setEditingId(null)}
        />
      )}

      {products.length === 0 && editingId !== 'new' && (
        <p className="text-sm text-slate-500">{strings.catalogo.sinProductos}</p>
      )}

      <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-slate-200 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2">{strings.catalogo.columnNombre}</th>
              <th className="px-4 py-2">{strings.catalogo.columnUnidad}</th>
              <th className="px-4 py-2">{strings.catalogo.columnPrecio}</th>
              <th className="px-4 py-2">{strings.catalogo.columnEstado}</th>
              <th className="px-4 py-2" />
            </tr>
          </thead>
          <tbody>
            {products.map((product) => (
              <Fragment key={product.id}>
                <tr className="border-b border-slate-100 last:border-0">
                  <td className="px-4 py-2">
                    {product.name}
                    {product.is_combo && (
                      <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                        {strings.catalogo.esCombo}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-2">{product.unit}</td>
                  <td className="px-4 py-2">${product.price.toLocaleString('es-CL')}</td>
                  <td className="px-4 py-2">
                    <span className={product.active ? 'text-emerald-600' : 'text-slate-400'}>
                      {product.active ? strings.catalogo.activo : strings.catalogo.inactivo}
                    </span>
                  </td>
                  <td className="space-x-3 px-4 py-2 text-right">
                    <button
                      onClick={() => setEditingId(product.id)}
                      className="text-xs font-medium text-slate-600 hover:text-slate-900"
                    >
                      {strings.catalogo.editar}
                    </button>
                    <button
                      onClick={() => handleToggleActive(product)}
                      className="text-xs font-medium text-slate-600 hover:text-slate-900"
                    >
                      {product.active ? strings.catalogo.desactivar : strings.catalogo.activar}
                    </button>
                  </td>
                </tr>
                {editingId === product.id && (
                  <tr>
                    <td colSpan={5} className="p-4">
                      <ProductForm
                        product={product}
                        allProducts={products}
                        onSaved={handleSaved}
                        onCancel={() => setEditingId(null)}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
