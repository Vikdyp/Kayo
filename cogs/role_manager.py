import discord
from discord.ext import commands

class RoleManager(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.role_combinations = [
            {
                'required_roles': ['Valorant', 'Chill'],
                'new_role': 'Valorant Chill'
            },
            {
                'required_roles': ['Valorant', 'Tryhard'],
                'new_role': 'Valorant Tryhard'
            },
            {
                'required_roles': ['Valorant', 'E-Sports'],
                'new_role': 'Valorant E-Sports'
            },
            {
                'required_roles': ['Rocket League', 'Chill'],
                'new_role': 'Rocket League Chill'
            },
            {
                'required_roles': ['Rocket League', 'Tryhard'],
                'new_role': 'Rocket League Tryhard'
            }
        ]

    async def check_roles(self, member):
        roles_to_remove = set()

        for combination in self.role_combinations:
            required_roles = combination['required_roles']
            new_role_name = combination['new_role']

            required_role_objects = [discord.utils.get(member.guild.roles, name=role) for role in required_roles]
            new_role = discord.utils.get(member.guild.roles, name=new_role_name)

            has_all_required_roles = all(role in member.roles for role in required_role_objects)

            if has_all_required_roles:
                if new_role and new_role not in member.roles:
                    await member.add_roles(new_role)

                for role in required_role_objects:
                    roles_to_remove.add(role)

        for role in roles_to_remove:
            if role in member.roles:
                await member.remove_roles(role)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        await self.check_roles(after)

async def setup(bot):
    await bot.add_cog(RoleManager(bot))
