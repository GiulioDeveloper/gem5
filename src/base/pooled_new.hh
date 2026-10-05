#ifndef __BASE_POOLED_NEW_HH__
#define __BASE_POOLED_NEW_HH__

#include <cstddef>
#include <new>

namespace gem5
{

/**
 * Class-specific operator new and delete that recycle freed objects of
 * one class through a per-thread free list instead of returning them to
 * the heap. A class the simulator creates and destroys at a high rate
 * (per instruction or per branch) derives from PooledNew<ThatClass>.
 *
 * Construction and destruction are unchanged; only where the memory
 * comes from differs, so simulation behavior cannot change. Objects of a
 * derived class with a different size use the global heap as before.
 * Freed memory stays in the pool for reuse and is never returned.
 */
template <class T> class PooledNew
{
  public:
    static void *
    operator new(std::size_t size)
    {
        static_assert(sizeof(T) >= sizeof(FreeNode),
                      "A pooled object must be able to hold a link.");
        if (size == sizeof(T) && freeList) {
            FreeNode *node = freeList;
            freeList = node->next;
            return node;
        }
        return ::operator new(size);
    }

    static void
    operator delete(void *ptr, std::size_t size)
    {
        if (size == sizeof(T)) {
            FreeNode *node = static_cast<FreeNode *>(ptr);
            node->next = freeList;
            freeList = node;
            return;
        }
        ::operator delete(ptr, size);
    }

  private:
    struct FreeNode
    {
        FreeNode *next;
    };

    static inline thread_local FreeNode *freeList = nullptr;
};

/**
 * A standard allocator that recycles single-element allocations (the
 * nodes of a std::list, for example) through a per-thread free list, the
 * way PooledNew does for a class. Larger allocations use the heap. All
 * instances are interchangeable, so containers using it swap and splice
 * as with std::allocator.
 */
template <class T> class PooledAllocator
{
  public:
    using value_type = T;

    PooledAllocator() noexcept = default;

    template <class U> PooledAllocator(const PooledAllocator<U> &) noexcept {}

    T *
    allocate(std::size_t n)
    {
        static_assert(sizeof(T) >= sizeof(FreeNode),
                      "A pooled element must be able to hold a link.");
        if (n == 1 && freeList) {
            FreeNode *node = freeList;
            freeList = node->next;
            return reinterpret_cast<T *>(node);
        }
        return static_cast<T *>(::operator new(n * sizeof(T)));
    }

    void
    deallocate(T *ptr, std::size_t n) noexcept
    {
        if (n == 1) {
            FreeNode *node = reinterpret_cast<FreeNode *>(ptr);
            node->next = freeList;
            freeList = node;
            return;
        }
        ::operator delete(ptr, n * sizeof(T));
    }

    template <class U>
    bool
    operator==(const PooledAllocator<U> &) const noexcept
    {
        return true;
    }

    template <class U>
    bool
    operator!=(const PooledAllocator<U> &) const noexcept
    {
        return false;
    }

  private:
    struct FreeNode
    {
        FreeNode *next;
    };

    static inline thread_local FreeNode *freeList = nullptr;
};

} // namespace gem5

#endif // __BASE_POOLED_NEW_HH__
