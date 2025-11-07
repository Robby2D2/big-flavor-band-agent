"""Quick test of smart_search SQL."""
import asyncio
from mcp_server import BigFlavorMCPServer


async def main():
    server = BigFlavorMCPServer(enable_rag=True)
    await server.initialize_rag()
    
    print("\n" + "=" * 60)
    print("Testing: sleep query")
    print("=" * 60)
    result = await server.smart_search("sleep", limit=10)
    print(f"\nResult: {result}")
    
    await server.db_manager.close()


if __name__ == "__main__":
    asyncio.run(main())
