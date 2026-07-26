import { useCallback, useState } from "react";
import {
  addToCart as apiAdd,
  clearCart as apiClear,
  getCart,
  removeCartItem,
  updateCartItem,
} from "@/data/api";

const EMPTY = { items: [], item_count: 0, total: 0 };

// Cart state backed by the server. Every mutation endpoint returns the full
// updated cart, so we just store whatever the API hands back.
export function useCart() {
  const [cart, setCart] = useState(EMPTY);

  // Load (or clear, on 401 after logout) the cart. Safe to call with no token.
  const refresh = useCallback(async () => {
    try {
      setCart(await getCart());
    } catch {
      setCart(EMPTY);
    }
  }, []);

  const add = useCallback(async (productId, quantity = 1) => {
    setCart(await apiAdd(productId, quantity));
  }, []);

  const setQuantity = useCallback(async (productId, quantity) => {
    setCart(await updateCartItem(productId, quantity));
  }, []);

  const remove = useCallback(async (productId) => {
    setCart(await removeCartItem(productId));
  }, []);

  const clear = useCallback(async () => {
    setCart(await apiClear());
  }, []);

  return { cart, refresh, add, setQuantity, remove, clear };
}
