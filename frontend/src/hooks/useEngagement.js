import { useCallback, useEffect, useState } from "react";
import {
  addWishlist,
  getRecentlyViewed,
  getWishlist,
  mapProduct,
  recordView as apiRecordView,
  removeWishlist,
} from "@/data/api";

// Server-backed wishlist + recently-viewed. Mounted inside Dashboard, so it
// loads once the user is signed in. Wishlist is tracked as an id list for cheap
// toggle checks; recently-viewed is the full product list for the carousel.
export function useEngagement() {
  const [wishlistIds, setWishlistIds] = useState([]);
  const [recentlyViewed, setRecentlyViewed] = useState([]);

  const refresh = useCallback(async () => {
    try {
      const [wish, recent] = await Promise.all([getWishlist(), getRecentlyViewed()]);
      setWishlistIds((wish.items || []).map((p) => p.id));
      setRecentlyViewed((recent.items || []).map(mapProduct));
    } catch {
      setWishlistIds([]);
      setRecentlyViewed([]);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const toggleWishlist = useCallback(
    async (productId) => {
      const wished = wishlistIds.includes(productId);
      // Optimistic: flip immediately, reconcile with the server response.
      setWishlistIds((prev) =>
        wished ? prev.filter((id) => id !== productId) : [...prev, productId]
      );
      try {
        const result = wished ? await removeWishlist(productId) : await addWishlist(productId);
        setWishlistIds((result.items || []).map((p) => p.id));
      } catch {
        // Revert on failure.
        setWishlistIds((prev) =>
          wished ? [...prev, productId] : prev.filter((id) => id !== productId)
        );
      }
    },
    [wishlistIds]
  );

  const recordView = useCallback(async (productId) => {
    try {
      const result = await apiRecordView(productId);
      setRecentlyViewed((result.items || []).map(mapProduct));
    } catch {
      /* non-critical */
    }
  }, []);

  return { wishlistIds, recentlyViewed, toggleWishlist, recordView };
}
